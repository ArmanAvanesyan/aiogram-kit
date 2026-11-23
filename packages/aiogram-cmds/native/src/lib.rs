//! CPU-only native boundaries. Python resolves all translator callbacks first.
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyString, PyStringMethods};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::sync::Mutex;

type Rows = Vec<(String, String)>;
type Profiles = Vec<(String, Vec<(String, Rows)>)>;
type Request = (String, String, String, String, String);
type Requests = Vec<Request>;
#[derive(Default)]
struct Fingerprints {
    requests: HashMap<Request, String>,
    // One of at most 256 retained derived hashes. Borrowed comparisons let the
    // single-target confirmation path avoid five String allocations per hit.
    last: Option<(Request, String)>,
}
type FingerprintCache = Mutex<Fingerprints>;
type BatchResult = Vec<String>;

pub fn resolve_profile(include: &[String], exclude: &[String], known: &[String]) -> Vec<String> {
    let excluded: HashSet<&str> = exclude.iter().map(String::as_str).collect();
    let names: HashSet<&str> = known.iter().map(String::as_str).collect();
    include
        .iter()
        .filter(|name| names.contains(name.as_str()) && !excluded.contains(name.as_str()))
        .cloned()
        .collect()
}

pub fn validate_rows(rows: &[(String, String)]) -> Result<(), String> {
    for (name, description) in rows {
        let mut chars = name.bytes();
        if !(1..=32).contains(&name.len())
            || !chars.next().is_some_and(|c| c.is_ascii_lowercase())
            || !chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'_')
        {
            return Err("Invalid resolved command name".into());
        }
        if !(1..=256).contains(&description.chars().count()) {
            return Err("Invalid resolved command description".into());
        }
    }
    Ok(())
}

#[derive(Serialize)]
struct Command<'a> {
    command: &'a str,
    description: &'a str,
}

pub fn encode_rows<S: AsRef<str>>(rows: &[(S, S)]) -> String {
    serde_json::to_string(
        &rows
            .iter()
            .map(|(command, description)| Command {
                command: command.as_ref(),
                description: description.as_ref(),
            })
            .collect::<Vec<_>>(),
    )
    .expect("strings always serialize")
}

pub fn fingerprint_encoded(
    bot: &str,
    scope: &str,
    language: &str,
    commands: &str,
) -> Result<String, String> {
    if bot.is_empty() || bot.starts_with('0') || !bot.bytes().all(|c| c.is_ascii_digit()) {
        return Err("A positive decimal bot identity is required".into());
    }
    // This boundary takes canonical Python-produced scope JSON. Retain legacy
    // Python NaN/Infinity spelling inside dictionaries rather than normalizing it.
    if !scope.starts_with('{') || !scope.ends_with('}') {
        return Err("Scope must be a canonical object".into());
    }
    let language_value: serde_json::Value =
        serde_json::from_str(language).map_err(|_| "Invalid language JSON")?;
    if !language_value.is_null() && !language_value.is_string() {
        return Err("Language must be string or null".into());
    }
    // Scope/language strings are canonicalized by Python, retaining its float,
    // arbitrary-integer and Unicode semantics without calling Python here.
    let value = format!(
        "{{\"bot_id\":{bot},\"commands\":{commands},\"language_code\":{language},\"scope\":{scope}}}"
    );
    Ok({
        const HEX: &[u8; 16] = b"0123456789abcdef";
        let digest = Sha256::digest(value.as_bytes());
        let mut encoded = String::with_capacity(64);
        for byte in digest {
            encoded.push(HEX[(byte >> 4) as usize] as char);
            encoded.push(HEX[(byte & 15) as usize] as char);
        }
        encoded
    })
}

#[pyclass(frozen)]
struct NativeSnapshot {
    profiles: HashMap<(String, String), (Rows, String)>,
    // Snapshot-local cache; no confirmation, delivery or business state is cached.
    fingerprints: FingerprintCache,
}

#[pymethods]
impl NativeSnapshot {
    fn resolve_one(
        &self,
        profile: &str,
        locale: &str,
        bot: &str,
        scope: &str,
        language: &str,
    ) -> PyResult<String> {
        let mut cache = self
            .fingerprints
            .lock()
            .map_err(|_| PyRuntimeError::new_err("Fingerprint cache poisoned"))?;
        if let Some((request, hash)) = &cache.last {
            if request.0 == profile
                && request.1 == locale
                && request.2 == bot
                && request.3 == scope
                && request.4 == language
            {
                return Ok(hash.clone());
            }
        }
        let request = (
            profile.to_owned(),
            locale.to_owned(),
            bot.to_owned(),
            scope.to_owned(),
            language.to_owned(),
        );
        let hash = self.resolve(request.clone(), &mut cache.requests)?;
        if profile.len() + locale.len() + bot.len() + scope.len() + language.len() <= 4096 {
            cache.last = Some((request, hash.clone()));
        }
        Ok(hash)
    }
    fn resolve_batch(&self, requests: Requests) -> PyResult<BatchResult> {
        let mut results = Vec::with_capacity(requests.len());
        let mut cache = self
            .fingerprints
            .lock()
            .map_err(|_| PyRuntimeError::new_err("Fingerprint cache poisoned"))?;
        for request in requests {
            results.push(self.resolve(request, &mut cache.requests)?);
        }
        Ok(results)
    }
}

impl NativeSnapshot {
    fn resolve(&self, request: Request, cache: &mut HashMap<Request, String>) -> PyResult<String> {
        if let Some(hash) = cache.get(&request) {
            return Ok(hash.clone());
        }
        let (profile, locale, bot, scope, language) = &request;
        let (_, encoded) = self
            .profiles
            .get(&(profile.clone(), locale.clone()))
            .ok_or_else(|| PyValueError::new_err("Unknown compiled profile/locale"))?;
        let hash =
            fingerprint_encoded(bot, scope, language, encoded).map_err(PyValueError::new_err)?;
        if profile.len() + locale.len() + bot.len() + scope.len() + language.len() <= 4096 {
            if cache.len() >= 255 {
                cache.clear();
            }
            cache.insert(request, hash.clone());
        }
        Ok(hash)
    }
}

#[pyfunction(name = "resolve_profile")]
fn resolve_profile_py(
    include: Vec<String>,
    exclude: Vec<String>,
    known: Vec<String>,
) -> Vec<String> {
    resolve_profile(&include, &exclude, &known)
}
#[pyfunction]
fn validate_commands(rows: Rows) -> PyResult<()> {
    validate_rows(&rows).map_err(PyValueError::new_err)
}
#[pyfunction]
fn fingerprint(
    bot_id: String,
    scope_json: String,
    language_json: String,
    rows: Vec<(Bound<'_, PyString>, Bound<'_, PyString>)>,
) -> PyResult<String> {
    // Borrow only while the input strings are alive and the GIL is held.
    // No borrowed reference escapes this call or enters a cache.
    let borrowed: PyResult<Vec<_>> = rows
        .iter()
        .map(|(command, description)| Ok((command.to_cow()?, description.to_cow()?)))
        .collect();
    fingerprint_encoded(
        &bot_id,
        &scope_json,
        &language_json,
        &encode_rows(&borrowed?),
    )
    .map_err(PyValueError::new_err)
}
#[pyfunction(name = "compile")]
fn compile_py(rows: Profiles) -> PyResult<NativeSnapshot> {
    let mut profiles = HashMap::new();
    for (profile, locales) in rows {
        for (locale, commands) in locales {
            validate_rows(&commands).map_err(PyValueError::new_err)?;
            let encoded = encode_rows(&commands);
            if profiles
                .insert((profile.clone(), locale), (commands, encoded))
                .is_some()
            {
                return Err(PyValueError::new_err("Duplicate profile/locale"));
            }
        }
    }
    Ok(NativeSnapshot {
        profiles,
        fingerprints: Mutex::new(Fingerprints::default()),
    })
}
#[pyfunction]
fn abi_version() -> u32 {
    1
}
#[pyfunction]
fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}
#[pymodule]
fn _aiogram_cmds_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(resolve_profile_py, module)?)?;
    module.add_function(wrap_pyfunction!(validate_commands, module)?)?;
    module.add_function(wrap_pyfunction!(fingerprint, module)?)?;
    module.add_function(wrap_pyfunction!(compile_py, module)?)?;
    module.add_function(wrap_pyfunction!(abi_version, module)?)?;
    module.add_function(wrap_pyfunction!(version, module)?)?;
    module.add_class::<NativeSnapshot>()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn preserves_duplicates_and_exclusions() {
        let input = vec!["a".into(), "a".into(), "b".into(), "missing".into()];
        assert_eq!(
            resolve_profile(&input, &["b".into()], &["a".into(), "b".into()]),
            vec!["a", "a"]
        );
    }
    #[test]
    fn validates_before_hashing() {
        assert!(validate_rows(&[("bad!".into(), "Description".into())]).is_err());
        assert!(fingerprint_encoded("0", "{}", "null", "[]").is_err());
        assert!(fingerprint_encoded("1", "[]", "null", "[]").is_err());
    }
}
