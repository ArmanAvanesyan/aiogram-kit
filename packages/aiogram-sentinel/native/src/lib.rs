//! Synchronous, process-local storage. Clocks and interval validation belong to Python.
use hashbrown::HashMap;
use std::collections::{VecDeque, hash_map::RandomState};
use std::sync::Mutex;

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyString};

// Borrow CPython's cached UTF-8 for ordinary strings. Surrogates use the exact
// previous str.encode(..., surrogatepass) contract, before any state mutation.
fn with_key<T>(
    key: &Bound<'_, PyString>,
    action: impl FnOnce(&[u8]) -> PyResult<T>,
) -> PyResult<T> {
    if let Ok(value) = key.to_str() {
        return action(value.as_bytes());
    }
    let encoded = key
        .py()
        .get_type::<PyString>()
        .call_method1("encode", (key, "utf-8", "surrogatepass"))?;
    action(encoded.cast::<PyBytes>()?.as_bytes())
}

#[derive(Default)]
pub struct RateState {
    pub counters: HashMap<Vec<u8>, VecDeque<f64>, RandomState>,
}

impl RateState {
    fn counter(&mut self, key: &[u8], window: f64, now: f64) -> &mut VecDeque<f64> {
        // One lookup, retaining std's keyed HashDoS-resistant RandomState.
        // Borrowed entry lookup copies key bytes only on first admission.
        let counter = self.counters.entry_ref(key).or_default();
        let cutoff = now - window;
        // Exact-boundary requests remain in the window, matching Python deque.
        while counter.front().is_some_and(|value| *value < cutoff) {
            counter.pop_front();
        }
        counter
    }

    pub fn allow(&mut self, key: &[u8], maximum: usize, window: f64, now: f64) -> bool {
        let counter = self.counter(key, window, now);
        if counter.len() < maximum {
            counter.push_back(now);
            true
        } else {
            false
        }
    }

    pub fn remaining(&mut self, key: &[u8], maximum: usize, window: f64, now: f64) -> usize {
        maximum.saturating_sub(self.counter(key, window, now).len())
    }

    pub fn increment(&mut self, key: &[u8], window: f64, now: f64) -> usize {
        let counter = self.counter(key, window, now);
        counter.push_back(now);
        counter.len()
    }

    pub fn count(&mut self, key: &[u8], now: f64) -> usize {
        self.counter(key, 60.0, now).len()
    }

    pub fn reset(&mut self, key: &[u8]) {
        if let Some(counter) = self.counters.get_mut(key) {
            counter.clear();
        }
    }
}

#[derive(Default)]
pub struct DebounceState {
    pub entries: HashMap<Vec<u8>, f64, RandomState>,
}

impl DebounceState {
    pub fn seen(&mut self, key: &[u8], window: f64, fingerprint: &[u8], now: f64) -> bool {
        // Preserve the legacy composite key and its interaction with raw-key helpers.
        let mut combined = Vec::with_capacity(key.len() + fingerprint.len() + 1);
        combined.extend_from_slice(key);
        combined.push(b':');
        combined.extend_from_slice(fingerprint);
        // Direct native callers already own this buffer: move it into an empty
        // entry rather than copying it through the borrowed SDK entry point.
        Self::mark_seen(self.entries.entry(combined).or_insert(0.0), window, now)
    }

    pub fn seen_key(&mut self, key: &[u8], window: f64, now: f64) -> bool {
        Self::mark_seen(self.entries.entry_ref(key).or_insert(0.0), window, now)
    }

    fn mark_seen(timestamp: &mut f64, window: f64, now: f64) -> bool {
        if *timestamp != 0.0 && *timestamp + window > now {
            true
        } else {
            *timestamp = now;
            false
        }
    }

    pub fn set(&mut self, key: &[u8], delay: f64, now: f64) {
        if delay <= 0.0 {
            self.entries.remove(key);
        } else {
            self.entries.insert(key.to_owned(), now + delay);
        }
    }

    pub fn active(&mut self, key: &[u8], now: f64) -> bool {
        let timestamp = *self.entries.get(key).unwrap_or(&0.0);
        if timestamp != 0.0 && timestamp >= now {
            true
        } else {
            self.entries.remove(key);
            false
        }
    }
}

#[pyclass(frozen)]
#[derive(Default)]
struct RateLimiterCore {
    state: Mutex<RateState>,
}

#[pymethods]
impl RateLimiterCore {
    #[new]
    fn new() -> Self {
        Self::default()
    }

    fn allow_text(
        &self,
        key: &Bound<'_, PyString>,
        maximum: usize,
        window: f64,
        now: f64,
    ) -> PyResult<bool> {
        with_key(key, |bytes| {
            Ok(self
                .state
                .lock()
                .map_err(poisoned)?
                .allow(bytes, maximum, window, now))
        })
    }
    fn allow(&self, key: &[u8], maximum: usize, window: f64, now: f64) -> PyResult<bool> {
        Ok(self
            .state
            .lock()
            .map_err(poisoned)?
            .allow(key, maximum, window, now))
    }
    fn remaining(&self, key: &[u8], maximum: usize, window: f64, now: f64) -> PyResult<usize> {
        Ok(self
            .state
            .lock()
            .map_err(poisoned)?
            .remaining(key, maximum, window, now))
    }
    fn increment(&self, key: &[u8], window: f64, now: f64) -> PyResult<usize> {
        Ok(self
            .state
            .lock()
            .map_err(poisoned)?
            .increment(key, window, now))
    }
    fn count(&self, key: &[u8], now: f64) -> PyResult<usize> {
        Ok(self.state.lock().map_err(poisoned)?.count(key, now))
    }
    fn reset(&self, key: &[u8]) -> PyResult<()> {
        self.state.lock().map_err(poisoned)?.reset(key);
        Ok(())
    }
    fn snapshot(&self) -> PyResult<Vec<(Vec<u8>, Vec<f64>)>> {
        Ok(self
            .state
            .lock()
            .map_err(poisoned)?
            .counters
            .iter()
            .map(|(key, values)| (key.clone(), values.iter().copied().collect()))
            .collect())
    }
}

#[pyclass(frozen)]
#[derive(Default)]
struct DebounceCore {
    state: Mutex<DebounceState>,
}

#[pymethods]
impl DebounceCore {
    #[new]
    fn new() -> Self {
        Self::default()
    }
    fn seen(&self, key: &[u8], window: f64, fingerprint: &[u8], now: f64) -> PyResult<bool> {
        Ok(self
            .state
            .lock()
            .map_err(poisoned)?
            .seen(key, window, fingerprint, now))
    }
    fn seen_text(&self, key: &Bound<'_, PyString>, window: f64, now: f64) -> PyResult<bool> {
        with_key(key, |bytes| {
            Ok(self
                .state
                .lock()
                .map_err(poisoned)?
                .seen_key(bytes, window, now))
        })
    }
    fn seen_key(&self, key: &[u8], window: f64, now: f64) -> PyResult<bool> {
        Ok(self
            .state
            .lock()
            .map_err(poisoned)?
            .seen_key(key, window, now))
    }

    fn set(&self, key: &[u8], delay: f64, now: f64) -> PyResult<()> {
        self.state.lock().map_err(poisoned)?.set(key, delay, now);
        Ok(())
    }
    fn active(&self, key: &[u8], now: f64) -> PyResult<bool> {
        Ok(self.state.lock().map_err(poisoned)?.active(key, now))
    }
    fn snapshot(&self) -> PyResult<Vec<(Vec<u8>, f64)>> {
        Ok(self
            .state
            .lock()
            .map_err(poisoned)?
            .entries
            .iter()
            .map(|(key, value)| (key.clone(), *value))
            .collect())
    }
}

fn poisoned<T>(_: std::sync::PoisonError<T>) -> PyErr {
    PyRuntimeError::new_err("Native memory lock poisoned; state cannot be safely reused")
}

#[pyfunction]
fn capabilities() -> (&'static str, u32, &'static str) {
    ("aiogram-sentinel-native", 1, env!("CARGO_PKG_VERSION"))
}

#[pymodule]
fn _aiogram_sentinel_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(capabilities, module)?)?;
    module.add_class::<RateLimiterCore>()?;
    module.add_class::<DebounceCore>()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rate_boundaries_and_destructive_window_changes() {
        let mut rate = RateState::default();
        assert!(rate.allow(b"key", 1, 10.0, 100.0));
        assert!(!rate.allow(b"key", 1, 10.0, 110.0));
        assert!(rate.allow(b"key", 1, 10.0, 110.00001));
        // A smaller requested window prunes this key only, just like Python.
        assert_eq!(rate.remaining(b"key", 1, 1.0, 112.0), 1);
        assert_eq!(rate.remaining(b"key", 1, 100.0, 112.0), 1);
    }

    #[test]
    fn quiet_keys_are_not_garbage_collected_for_other_keys() {
        let mut rate = RateState::default();
        rate.allow(b"old", 5, 5.0, 1.0);
        rate.allow(b"other", 5, 5.0, 100.0);
        assert_eq!(rate.remaining(b"old", 5, 1000.0, 100.0), 4);
    }

    #[test]
    fn borrowed_entries_reuse_keys_and_preserve_reset() {
        let mut state = RateState::default();
        for index in 0..1024 {
            let key = format!("user:{index}");
            assert!(state.allow(key.as_bytes(), 2, 60.0, 100.0));
            assert!(state.allow(key.as_bytes(), 2, 60.0, 100.0));
            assert!(!state.allow(key.as_bytes(), 2, 60.0, 100.0));
        }
        assert_eq!(state.counters.len(), 1024);
        state.reset(b"user:17");
        assert_eq!(state.remaining(b"user:17", 2, 60.0, 100.0), 2);
        assert_eq!(state.remaining(b"user:18", 2, 60.0, 100.0), 0);
    }

    #[test]
    fn debounce_helpers_keep_composite_key_aliasing() {
        let mut state = DebounceState::default();
        state.set(b"key:fp", 5.0, 100.0);
        assert!(state.seen(b"key", 10.0, b"fp", 110.0));
        assert!(!state.seen(b"key", 10.0, b"fp", 115.0));
        state.set(b"key:fp", 0.0, 116.0);
        assert!(!state.seen(b"key", 10.0, b"fp", 116.0));
    }

    #[test]
    fn debounce_zero_and_inclusive_helper_boundaries() {
        let mut state = DebounceState::default();
        assert!(!state.seen(b"key", 10.0, b"fp", 0.0));
        assert!(!state.seen(b"key", 10.0, b"fp", 0.0));
        assert!(!state.seen(b"key", 10.0, b"fp", 1.0));
        assert!(state.seen(b"key", 10.0, b"fp", 10.999));
        assert!(!state.seen(b"key", 10.0, b"fp", 11.0));
        state.set(b"key", 5.0, 10.0);
        assert!(state.active(b"key", 15.0));
        assert!(!state.active(b"key", 15.0001));
    }
}
