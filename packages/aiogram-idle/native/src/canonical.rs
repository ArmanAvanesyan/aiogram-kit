//! One native boundary owns canonical traversal, JSON bytes and SHA256.
//! CPython formats floating-point numbers and exceptional scalar domains.
use pyo3::create_exception;
use pyo3::exceptions::{PyRecursionError, PyRuntimeError, PyValueError};
create_exception!(_aiogram_idle_native, InvalidJson, PyValueError);
create_exception!(_aiogram_idle_native, UnsupportedJson, PyValueError);
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyFloat, PyInt, PyList, PyString, PyTuple, PyType};
use sha2::{Digest, Sha256};

#[pyclass(frozen)]
pub struct Canonicalizer {
    memo: std::sync::Mutex<Memo>,
    schemas: std::sync::Arc<std::collections::HashMap<usize, Schema>>,
    proxy_type: Py<PyAny>,
    enum_type: Py<PyAny>,
    mapping_type: Py<PyAny>,
    fields: Py<PyAny>,
    datetime_type: Option<Py<PyAny>>,
    view_type: Option<Py<PyAny>>,
    render_type: Option<Py<PyAny>>,
    dumps: Py<PyAny>,
    escape: Py<PyAny>,
    referents: Py<PyAny>,
    int_repr: Py<PyAny>,
    float_repr: Py<PyAny>,
}

#[pymethods]
impl Canonicalizer {
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature=(enum_type, mapping_type, fields, datetime_type=None, view_type=None, render_type=None, immutable_types=None))]
    fn new(
        py: Python<'_>,
        enum_type: Py<PyAny>,
        mapping_type: Py<PyAny>,
        fields: Py<PyAny>,
        datetime_type: Option<Py<PyAny>>,
        view_type: Option<Py<PyAny>>,
        render_type: Option<Py<PyAny>>,
        immutable_types: Option<Py<PyAny>>,
    ) -> PyResult<Self> {
        let json = py.import("json")?;
        let mut schemas = std::collections::HashMap::new();
        if let Some(types) = immutable_types {
            for ty in types.bind(py).try_iter()? {
                let ty = ty?;
                if !ty
                    .getattr("__dataclass_params__")?
                    .getattr("frozen")?
                    .is_truthy()?
                {
                    return Err(PyValueError::new_err(
                        "Immutable schemas must be frozen dataclasses",
                    ));
                }
                let names = fields
                    .bind(py)
                    .call1((&ty,))?
                    .try_iter()?
                    .map(|field| field?.getattr("name")?.extract::<String>())
                    .collect::<PyResult<Vec<_>>>()?;
                schemas.insert(
                    ty.as_ptr() as usize,
                    Schema {
                        _class: ty.unbind(),
                        names,
                    },
                );
            }
        }
        Ok(Self {
            memo: std::sync::Mutex::new(Memo::default()),
            schemas: std::sync::Arc::new(schemas),
            proxy_type: py.import("types")?.getattr("MappingProxyType")?.unbind(),
            enum_type,
            mapping_type,
            fields,
            datetime_type,
            view_type,
            render_type,
            dumps: json.getattr("dumps")?.unbind(),
            escape: json
                .getattr("encoder")?
                .getattr("encode_basestring_ascii")?
                .unbind(),
            referents: py.import("gc")?.getattr("get_referents")?.unbind(),
            int_repr: py.get_type::<PyInt>().getattr("__repr__")?.unbind(),
            float_repr: py.get_type::<PyFloat>().getattr("__repr__")?.unbind(),
        })
    }
    fn fork(&self, py: Python<'_>) -> Self {
        Self {
            memo: std::sync::Mutex::new(Memo::default()),
            schemas: self.schemas.clone(),
            proxy_type: self.proxy_type.clone_ref(py),
            enum_type: self.enum_type.clone_ref(py),
            mapping_type: self.mapping_type.clone_ref(py),
            fields: self.fields.clone_ref(py),
            datetime_type: self.datetime_type.as_ref().map(|x| x.clone_ref(py)),
            view_type: self.view_type.as_ref().map(|x| x.clone_ref(py)),
            render_type: self.render_type.as_ref().map(|x| x.clone_ref(py)),
            dumps: self.dumps.clone_ref(py),
            escape: self.escape.clone_ref(py),
            referents: self.referents.clone_ref(py),
            int_repr: self.int_repr.clone_ref(py),
            float_repr: self.float_repr.clone_ref(py),
        }
    }
    fn fingerprint(&self, value: &Bound<'_, PyAny>) -> PyResult<String> {
        let mut bytes = Vec::with_capacity(256);
        self.write(value, &mut bytes, 0)?;
        let digest = Sha256::digest(bytes);
        const HEX: &[u8; 16] = b"0123456789abcdef";
        let mut result = String::with_capacity(64);
        for byte in digest {
            result.push(HEX[(byte >> 4) as usize] as char);
            result.push(HEX[(byte & 15) as usize] as char);
        }
        Ok(result)
    }
    fn clear_cache(&self) -> PyResult<()> {
        let old = {
            let mut memo = self
                .memo
                .lock()
                .map_err(|_| PyRuntimeError::new_err("JSON codec cache poisoned"))?;
            memo.bytes = 0;
            std::mem::take(&mut memo.entries)
        };
        drop(old);
        Ok(())
    }
    fn cache_stats(&self) -> PyResult<(usize, usize)> {
        let memo = self
            .memo
            .lock()
            .map_err(|_| PyRuntimeError::new_err("JSON codec cache poisoned"))?;
        Ok((memo.entries.len(), memo.bytes))
    }
    fn freeze(
        &self,
        value: &Bound<'_, PyAny>,
        proxy: &Bound<'_, PyAny>,
        style: &str,
    ) -> PyResult<Option<(Py<PyAny>, usize)>> {
        if style != "nav" && style != "idle" {
            return Err(PyValueError::new_err("Unknown JSON freeze policy"));
        }
        if !proxy.is(self.proxy_type.bind(value.py())) {
            return Err(PyValueError::new_err("Unsupported proxy type"));
        }
        let nav = style == "nav";
        if let Some(result) = self.memo_frozen(value, nav)? {
            return Ok(Some(result));
        }
        match self.frozen_size(value, proxy, nav, 0) {
            Ok(result) => {
                if result.0.bind(value.py()).get_type().is(proxy)
                    || result.0.bind(value.py()).is_instance_of::<PyTuple>()
                {
                    self.memo_register(result.0.bind(value.py()), result.1, u8::from(nav), None)?;
                }
                Ok(Some(result))
            }
            Err(error) if error.is_instance_of::<UnsupportedJson>(value.py()) => Ok(None),
            Err(error) => Err(error),
        }
    }
}

impl Canonicalizer {
    fn quoted(&self, value: &Bound<'_, PyAny>, out: &mut Vec<u8>) -> PyResult<()> {
        let text = value.downcast::<PyString>()?;
        if let Ok(text) = text.to_str() {
            out.push(b'"');
            for ch in text.chars() {
                match ch {
                    '"' => out.extend_from_slice(b"\\\""),
                    '\\' => out.extend_from_slice(b"\\\\"),
                    '\x08' => out.extend_from_slice(b"\\b"),
                    '\x0c' => out.extend_from_slice(b"\\f"),
                    '\n' => out.extend_from_slice(b"\\n"),
                    '\r' => out.extend_from_slice(b"\\r"),
                    '\t' => out.extend_from_slice(b"\\t"),
                    ' '..='~' => out.push(ch as u8),
                    _ => {
                        const HEX: &[u8; 16] = b"0123456789abcdef";
                        let mut units = [0u16; 2];
                        for unit in ch.encode_utf16(&mut units) {
                            out.extend_from_slice(b"\\u");
                            for shift in [12, 8, 4, 0] {
                                out.push(HEX[((*unit >> shift) & 15) as usize]);
                            }
                        }
                    }
                }
            }
            out.push(b'"');
        } else {
            // Opaque low-level identities may contain surrogate code points.
            let escaped = self.escape.bind(value.py()).call1((value,))?;
            out.extend_from_slice(escaped.downcast::<PyString>()?.to_str()?.as_bytes());
        }
        Ok(())
    }
    fn fallback(&self, value: &Bound<'_, PyAny>, out: &mut Vec<u8>) -> PyResult<()> {
        let py = value.py();
        let kwargs = PyDict::new(py);
        kwargs.set_item("sort_keys", true)?;
        kwargs.set_item("allow_nan", false)?;
        kwargs.set_item("separators", (",", ":"))?;
        let raw = self.dumps.bind(py).call((value,), Some(&kwargs))?;
        out.extend_from_slice(raw.downcast::<PyString>()?.to_str()?.as_bytes());
        Ok(())
    }
    fn scalar(&self, value: &Bound<'_, PyAny>, out: &mut Vec<u8>) -> PyResult<bool> {
        if value.is_none() {
            out.extend_from_slice(b"null");
            return Ok(true);
        }
        if value.is_instance_of::<PyBool>() {
            out.extend_from_slice(if value.is_truthy()? {
                b"true"
            } else {
                b"false"
            });
            return Ok(true);
        }
        if value.is_instance_of::<PyString>() {
            self.quoted(value, out)?;
            return Ok(true);
        }
        if value.is_instance_of::<PyInt>() {
            if let Ok(n) = value.extract::<i64>() {
                out.extend_from_slice(n.to_string().as_bytes());
            } else {
                let text = self.int_repr.bind(value.py()).call1((value,))?;
                out.extend_from_slice(text.downcast::<PyString>()?.to_str()?.as_bytes());
            }
            return Ok(true);
        }
        if value.is_instance_of::<PyFloat>() {
            if !value.extract::<f64>()?.is_finite() {
                self.fallback(value, out)?;
                return Ok(true);
            }
            let text = self.float_repr.bind(value.py()).call1((value,))?;
            out.extend_from_slice(text.downcast::<PyString>()?.to_str()?.as_bytes());
            return Ok(true);
        }
        Ok(false)
    }
    fn object(&self, value: &Bound<'_, PyDict>, out: &mut Vec<u8>, depth: usize) -> PyResult<()> {
        let keys = PyList::new(value.py(), value.keys().iter())?;
        keys.call_method0("sort")?;
        out.push(b'{');
        for (index, key) in keys.iter().enumerate() {
            if index != 0 {
                out.push(b',');
            }
            self.quoted(&key, out)?;
            out.push(b':');
            self.write(
                &value.get_item(&key)?.ok_or_else(|| {
                    PyRuntimeError::new_err("dictionary changed during canonicalization")
                })?,
                out,
                depth + 1,
            )?;
        }
        out.push(b'}');
        Ok(())
    }
    fn write(&self, value: &Bound<'_, PyAny>, out: &mut Vec<u8>, depth: usize) -> PyResult<()> {
        let candidate = value.get_type().is(self.proxy_type.bind(value.py()))
            || value.is_instance_of::<PyTuple>()
            || self
                .schemas
                .contains_key(&(value.get_type().as_ptr() as usize));
        let memo = if candidate {
            self.memo_encoded(value)?
        } else {
            None
        };
        if let Some((_, Some(ref bytes))) = memo {
            out.extend_from_slice(bytes);
            return Ok(());
        }
        let start = out.len();
        self.write_uncached(value, out, depth)?;
        if let Some((nav, None)) = memo {
            self.memo_encode(value, nav, &out[start..])?;
        } else if memo.is_none()
            && self
                .schemas
                .contains_key(&(value.get_type().as_ptr() as usize))
            && self.trusted(value, 0)?
        {
            let encoded: Encoded = std::sync::Arc::from(&out[start..]);
            self.memo_register(value, 0, 2, Some(encoded))?;
        }
        Ok(())
    }
    fn write_uncached(
        &self,
        value: &Bound<'_, PyAny>,
        out: &mut Vec<u8>,
        depth: usize,
    ) -> PyResult<()> {
        if depth > 128 {
            return Err(PyRecursionError::new_err(
                "maximum recursion depth exceeded during canonicalization",
            ));
        }
        let py = value.py();
        let ty = value.get_type();
        if value.is_none()
            || ty.is(py.get_type::<PyString>())
            || ty.is(py.get_type::<PyInt>())
            || ty.is(py.get_type::<PyFloat>())
            || ty.is(py.get_type::<PyBool>())
        {
            self.scalar(value, out)?;
            return Ok(());
        }
        if let Some(datetime) = &self.datetime_type {
            if value.is_instance(datetime.bind(py))? {
                return self.fallback(&value.call_method0("isoformat")?, out);
            }
        }
        if value.is_instance(self.enum_type.bind(py))? {
            // _canonical deliberately does not recurse into an Enum's value.
            let inner = value.getattr("value")?;
            if self.scalar(&inner, out)? {
                return Ok(());
            }
            return self.fallback(&inner, out);
        }
        let normalized = if let (Some(view), Some(render)) = (&self.view_type, &self.render_type) {
            if value.is_instance(view.bind(py))?
                && value.getattr("render_status")?.eq("complete")?
            {
                Some(render.bind(py).call1((
                    value.getattr("view_id")?,
                    value.getattr("messages")?,
                    value.getattr("reply_keyboard_key")?,
                    value.getattr("locale")?,
                    value.getattr("reply_keyboard_locale")?,
                ))?)
            } else {
                None
            }
        } else {
            None
        };
        let value = normalized.as_ref().unwrap_or(value);
        if !value.is_instance_of::<PyType>() && value.get_type().hasattr("__dataclass_fields__")? {
            let dict = PyDict::new(py);
            if let Some(schema) = self.schemas.get(&(value.get_type().as_ptr() as usize)) {
                for name in &schema.names {
                    dict.set_item(name, value.getattr(name.as_str())?)?;
                }
            } else {
                for field in self.fields.bind(py).call1((value,))?.try_iter()? {
                    let name = field?.getattr("name")?;
                    dict.set_item(&name, value.getattr(name.downcast::<PyString>()?)?)?;
                }
            }
            return self.object(&dict, out, depth);
        }
        if value.is_instance_of::<PyDict>() || value.is_instance(self.mapping_type.bind(py))? {
            let dict = PyDict::new(py);
            for pair in value.call_method0("items")?.try_iter()? {
                let pair = pair?;
                dict.set_item(pair.get_item(0)?.str()?, pair.get_item(1)?)?;
            }
            return self.object(&dict, out, depth);
        }
        if value.is_instance_of::<PyList>() || value.is_instance_of::<PyTuple>() {
            out.push(b'[');
            for (index, child) in value.try_iter()?.enumerate() {
                if index != 0 {
                    out.push(b',');
                }
                self.write(&child?, out, depth + 1)?;
            }
            out.push(b']');
            return Ok(());
        }
        if self.scalar(value, out)? {
            return Ok(());
        }
        self.fallback(value, out)
    }
}
impl Canonicalizer {
    fn json_dict<'py>(
        &self,
        value: &Bound<'py, PyAny>,
        proxy: &Bound<'py, PyAny>,
    ) -> PyResult<Option<Bound<'py, PyDict>>> {
        let py = value.py();
        if value.get_type().is(py.get_type::<PyDict>()) {
            return Ok(Some(value.downcast::<PyDict>()?.clone()));
        }
        if value.get_type().is(proxy) {
            // Public one-level GC traversal does not invoke a custom backing map.
            let refs = self.referents.bind(py).call1((value,))?;
            let refs = refs.downcast::<PyList>()?;
            if refs.len() == 1 {
                let backing = refs.get_item(0)?;
                if backing.get_type().is(py.get_type::<PyDict>()) {
                    return Ok(Some(backing.downcast::<PyDict>()?.clone()));
                }
            }
        }
        Ok(None)
    }
    fn string_size(text: &str, ascii: bool) -> usize {
        2 + text
            .chars()
            .map(|ch| match ch {
                '"' | '\\' | '\x08' | '\x0c' | '\n' | '\r' | '\t' => 2,
                '\x00'..='\x1f' => 6,
                '\x7f'.. if ascii => {
                    if ch as u32 > 0xffff {
                        12
                    } else {
                        6
                    }
                }
                _ => ch.len_utf8(),
            })
            .sum::<usize>()
    }
    fn frozen_size(
        &self,
        value: &Bound<'_, PyAny>,
        proxy: &Bound<'_, PyAny>,
        nav: bool,
        depth: usize,
    ) -> PyResult<(Py<PyAny>, usize)> {
        if depth > 32 {
            return Err(InvalidJson::new_err(if nav {
                "JSON nesting exceeds the supported depth"
            } else {
                "JSON nesting exceeds limit"
            }));
        }
        let py = value.py();
        let ty = value.get_type();
        if ty.is(py.get_type::<PyString>()) {
            let text = value.downcast::<PyString>()?.to_str().map_err(|_| {
                InvalidJson::new_err(if nav {
                    "JSON strings must contain valid Unicode scalars"
                } else {
                    "JSON string must contain valid UTF-8 Unicode scalars"
                })
            })?;
            return Ok((value.clone().unbind(), Self::string_size(text, !nav)));
        }
        if value.is_none() {
            return Ok((value.clone().unbind(), 4));
        }
        if ty.is(py.get_type::<PyBool>()) {
            return Ok((
                value.clone().unbind(),
                if value.is_truthy()? { 4 } else { 5 },
            ));
        }
        if ty.is(py.get_type::<PyInt>()) {
            // Large integers retain Python's configured decimal conversion limit
            // and its validation-before-serialization error order.
            let n = value
                .extract::<i64>()
                .map_err(|_| UnsupportedJson::new_err(()))?;
            return Ok((value.clone().unbind(), n.to_string().len()));
        }
        if ty.is(py.get_type::<PyFloat>()) {
            if !value.extract::<f64>()?.is_finite() {
                return Err(InvalidJson::new_err("JSON numbers must be finite"));
            }
            let size = self
                .float_repr
                .bind(py)
                .call1((value,))?
                .downcast::<PyString>()?
                .to_str()?
                .len();
            return Ok((value.clone().unbind(), size));
        }
        if let Some(dict) = self.json_dict(value, proxy)? {
            let items = dict.items();
            if nav {
                // Nav checks all keys before visiting values; preserve error order.
                for pair in items.iter() {
                    if !pair.get_item(0)?.get_type().is(py.get_type::<PyString>()) {
                        return Err(UnsupportedJson::new_err(()));
                    }
                }
                for pair in items.iter() {
                    pair.get_item(0)?
                        .downcast::<PyString>()?
                        .to_str()
                        .map_err(|_| {
                            InvalidJson::new_err(
                                "JSON object keys must contain valid Unicode scalars",
                            )
                        })?;
                }
            }
            let result = PyDict::new(py);
            let mut size = 2;
            for (index, pair) in items.iter().enumerate() {
                let key = pair.get_item(0)?;
                if !key.get_type().is(py.get_type::<PyString>()) {
                    return Err(UnsupportedJson::new_err(()));
                }
                let text = key.downcast::<PyString>()?.to_str().map_err(|_| {
                    InvalidJson::new_err(if nav {
                        "JSON object keys must contain valid Unicode scalars"
                    } else {
                        "JSON key must contain valid UTF-8 Unicode scalars"
                    })
                })?;
                let (child, child_size) =
                    self.frozen_size(&pair.get_item(1)?, proxy, nav, depth + 1)?;
                if index != 0 {
                    size += 2;
                }
                size += Self::string_size(text, !nav) + 2 + child_size;
                result.set_item(key, child)?;
            }
            return Ok((proxy.call1((result,))?.unbind(), size));
        }
        if ty.is(py.get_type::<PyTuple>()) || ty.is(py.get_type::<PyList>()) {
            let mut result = Vec::new();
            let mut size = 2;
            for (index, child) in value.try_iter()?.enumerate() {
                let (child, child_size) = self.frozen_size(&child?, proxy, nav, depth + 1)?;
                if index != 0 {
                    size += 2;
                }
                size += child_size;
                result.push(child);
            }
            return Ok((PyTuple::new(py, result)?.into_any().unbind(), size));
        }
        Err(UnsupportedJson::new_err(()))
    }
}
type Encoded = std::sync::Arc<[u8]>;
type MemoLookup = Option<(u8, Option<Encoded>)>;
const MEMO_LIMIT: usize = 128;
const MEMO_BYTES: usize = 1_048_576;
struct MemoEntry {
    value: Py<PyAny>,
    size: usize,
    encoded: Option<Encoded>,
}
#[derive(Default)]
struct Memo {
    entries: std::collections::HashMap<(usize, u8), MemoEntry>,
    bytes: usize,
}
impl Canonicalizer {
    fn memo_frozen(
        &self,
        value: &Bound<'_, PyAny>,
        nav: bool,
    ) -> PyResult<Option<(Py<PyAny>, usize)>> {
        let memo = self
            .memo
            .lock()
            .map_err(|_| PyRuntimeError::new_err("JSON codec cache poisoned"))?;
        Ok(memo
            .entries
            .get(&(value.as_ptr() as usize, u8::from(nav)))
            .map(|entry| (entry.value.clone_ref(value.py()), entry.size)))
    }
    fn memo_register(
        &self,
        value: &Bound<'_, PyAny>,
        size: usize,
        nav: u8,
        encoded: Option<Encoded>,
    ) -> PyResult<()> {
        let retained = size + encoded.as_ref().map_or(0, |bytes| bytes.len());
        if retained > MEMO_BYTES {
            return Ok(());
        }
        let key = (value.as_ptr() as usize, nav);
        let evicted = {
            let mut memo = self
                .memo
                .lock()
                .map_err(|_| PyRuntimeError::new_err("JSON codec cache poisoned"))?;
            if memo.entries.contains_key(&key) {
                return Ok(());
            }
            let evicted = if memo.entries.len() >= MEMO_LIMIT || memo.bytes + retained > MEMO_BYTES
            {
                memo.bytes = 0;
                Some(std::mem::take(&mut memo.entries))
            } else {
                None
            };
            memo.entries.insert(
                key,
                MemoEntry {
                    value: value.clone().unbind(),
                    size,
                    encoded,
                },
            );
            memo.bytes += retained;
            evicted
        };
        // Python references are released outside the cache mutex.
        drop(evicted);
        Ok(())
    }
    fn memo_encoded(&self, value: &Bound<'_, PyAny>) -> PyResult<MemoLookup> {
        let memo = self
            .memo
            .lock()
            .map_err(|_| PyRuntimeError::new_err("JSON codec cache poisoned"))?;
        for nav in [0, 1, 2] {
            if let Some(entry) = memo.entries.get(&(value.as_ptr() as usize, nav)) {
                return Ok(Some((nav, entry.encoded.clone())));
            }
        }
        Ok(None)
    }
    fn memo_encode(&self, value: &Bound<'_, PyAny>, nav: u8, encoded: &[u8]) -> PyResult<()> {
        let mut memo = self
            .memo
            .lock()
            .map_err(|_| PyRuntimeError::new_err("JSON codec cache poisoned"))?;
        if memo.bytes + encoded.len() > MEMO_BYTES {
            return Ok(());
        }
        if let Some(entry) = memo.entries.get_mut(&(value.as_ptr() as usize, nav)) {
            if entry.encoded.is_none() {
                entry.encoded = Some(std::sync::Arc::from(encoded));
                memo.bytes += encoded.len();
            }
        }
        Ok(())
    }
}

struct Schema {
    _class: Py<PyAny>,
    names: Vec<String>,
}
impl Canonicalizer {
    fn trusted(&self, value: &Bound<'_, PyAny>, depth: usize) -> PyResult<bool> {
        if depth > 128 {
            return Ok(false);
        }
        let py = value.py();
        let ty = value.get_type();
        if value.is_none()
            || ty.is(py.get_type::<PyString>())
            || ty.is(py.get_type::<PyFloat>())
            || ty.is(py.get_type::<PyBool>())
        {
            return Ok(true);
        }
        // Large decimal conversion depends on Python's runtime digit limit.
        // Keep those values uncached so a later policy change is observed.
        if ty.is(py.get_type::<PyInt>()) {
            return Ok(value.extract::<i64>().is_ok());
        }
        if ty.is(self.proxy_type.bind(py)) {
            return Ok(self.memo_encoded(value)?.is_some());
        }
        if ty.is(py.get_type::<PyTuple>()) {
            for child in value.try_iter()? {
                if !self.trusted(&child?, depth + 1)? {
                    return Ok(false);
                }
            }
            return Ok(true);
        }
        if let Some(schema) = self.schemas.get(&(ty.as_ptr() as usize)) {
            for name in &schema.names {
                if !self.trusted(&value.getattr(name.as_str())?, depth + 1)? {
                    return Ok(false);
                }
            }
            return Ok(true);
        }
        Ok(false)
    }
}
