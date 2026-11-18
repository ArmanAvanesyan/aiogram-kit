//! Strict single-pass materialization, without an intermediate serde Value tree.
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyInt, PyList, PyString};

fn invalid(message: &str) -> PyErr {
    PyValueError::new_err(message.to_owned())
}

pub fn parse(py: Python<'_>, raw: &str, max_bytes: usize, max_depth: usize) -> PyResult<Py<PyAny>> {
    if max_depth > 512 {
        return Err(invalid("JSON nesting policy exceeds supported bound"));
    }
    if raw.len() > max_bytes {
        return Err(invalid("JSON exceeds byte limit"));
    }
    let mut parser = Parser {
        py,
        bytes: raw.as_bytes(),
        at: 0,
        max_depth,
    };
    let value = parser.value(0)?;
    parser.ws();
    if parser.at != parser.bytes.len() {
        return Err(invalid("Trailing JSON data"));
    }
    Ok(value)
}

struct Parser<'a, 'py> {
    py: Python<'py>,
    bytes: &'a [u8],
    at: usize,
    max_depth: usize,
}

impl<'py> Parser<'_, 'py> {
    fn ws(&mut self) {
        while self
            .bytes
            .get(self.at)
            .is_some_and(|c| matches!(c, b' ' | b'\t' | b'\r' | b'\n'))
        {
            self.at += 1;
        }
    }
    fn take(&mut self, byte: u8) -> PyResult<()> {
        self.ws();
        if self.bytes.get(self.at) != Some(&byte) {
            return Err(invalid("Malformed JSON delimiter"));
        }
        self.at += 1;
        Ok(())
    }
    fn string(&mut self) -> PyResult<Bound<'py, PyString>> {
        self.ws();
        let start = self.at;
        self.take(b'"')?;
        let mut escaped = false;
        let mut needs_decode = false;
        while let Some(&byte) = self.bytes.get(self.at) {
            self.at += 1;
            if !escaped && byte == b'"' {
                if !needs_decode {
                    let text = std::str::from_utf8(&self.bytes[start + 1..self.at - 1])
                        .map_err(|_| invalid("Invalid UTF-8"))?;
                    return Ok(PyString::new(self.py, text));
                }
                let text: String = serde_json::from_slice(&self.bytes[start..self.at])
                    .map_err(|_| invalid("Invalid JSON string or Unicode"))?;
                return Ok(PyString::new(self.py, &text));
            }
            if byte < 32 {
                return Err(invalid("Unescaped JSON control character"));
            }
            if byte == b'\\' {
                needs_decode = true;
            }
            escaped = !escaped && byte == b'\\';
        }
        Err(invalid("Unterminated JSON string"))
    }
    fn number(&mut self) -> PyResult<Py<PyAny>> {
        let start = self.at;
        if self.bytes.get(self.at) == Some(&b'-') {
            self.at += 1;
        }
        match self.bytes.get(self.at) {
            Some(b'0') => self.at += 1,
            Some(b'1'..=b'9') => {
                self.at += 1;
                while self.bytes.get(self.at).is_some_and(u8::is_ascii_digit) {
                    self.at += 1;
                }
            }
            _ => return Err(invalid("Malformed JSON scalar")),
        }
        let mut float = false;
        if self.bytes.get(self.at) == Some(&b'.') {
            float = true;
            self.at += 1;
            let digits = self.at;
            while self.bytes.get(self.at).is_some_and(u8::is_ascii_digit) {
                self.at += 1;
            }
            if self.at == digits {
                return Err(invalid("Malformed JSON scalar"));
            }
        }
        if self
            .bytes
            .get(self.at)
            .is_some_and(|c| matches!(c, b'e' | b'E'))
        {
            float = true;
            self.at += 1;
            if self
                .bytes
                .get(self.at)
                .is_some_and(|c| matches!(c, b'+' | b'-'))
            {
                self.at += 1;
            }
            let digits = self.at;
            while self.bytes.get(self.at).is_some_and(u8::is_ascii_digit) {
                self.at += 1;
            }
            if self.at == digits {
                return Err(invalid("Malformed JSON scalar"));
            }
        }
        let text = std::str::from_utf8(&self.bytes[start..self.at])
            .map_err(|_| invalid("Invalid UTF-8"))?;
        if float {
            let value = text
                .parse::<f64>()
                .map_err(|_| invalid("Malformed JSON scalar"))?;
            if !value.is_finite() {
                return Err(invalid("Non-finite JSON number"));
            }
            return Ok(value.into_pyobject(self.py)?.into_any().unbind());
        }
        if let Ok(value) = text.parse::<i64>() {
            return Ok(value.into_pyobject(self.py)?.into_any().unbind());
        }
        if let Ok(value) = text.parse::<u64>() {
            return Ok(value.into_pyobject(self.py)?.into_any().unbind());
        }
        // Calling Python's integer constructor retains its configured digit limit.
        Ok(self
            .py
            .get_type::<PyInt>()
            .call1((text,))?
            .into_any()
            .unbind())
    }
    fn value(&mut self, depth: usize) -> PyResult<Py<PyAny>> {
        if depth > self.max_depth {
            return Err(invalid("JSON nesting limit exceeded"));
        }
        self.ws();
        match self.bytes.get(self.at).copied() {
            Some(b'{') => {
                self.at += 1;
                let result = PyDict::new(self.py);
                self.ws();
                if self.bytes.get(self.at) == Some(&b'}') {
                    self.at += 1;
                    return Ok(result.into_any().unbind());
                }
                loop {
                    let key = self.string()?;
                    if result.contains(&key)? {
                        return Err(invalid("Duplicate JSON object key"));
                    }
                    self.take(b':')?;
                    result.set_item(key, self.value(depth + 1)?)?;
                    self.ws();
                    if self.bytes.get(self.at) == Some(&b'}') {
                        self.at += 1;
                        break;
                    }
                    self.take(b',')?;
                }
                Ok(result.into_any().unbind())
            }
            Some(b'[') => {
                self.at += 1;
                let result = PyList::empty(self.py);
                self.ws();
                if self.bytes.get(self.at) == Some(&b']') {
                    self.at += 1;
                    return Ok(result.into_any().unbind());
                }
                loop {
                    result.append(self.value(depth + 1)?)?;
                    self.ws();
                    if self.bytes.get(self.at) == Some(&b']') {
                        self.at += 1;
                        break;
                    }
                    self.take(b',')?;
                }
                Ok(result.into_any().unbind())
            }
            Some(b'"') => Ok(self.string()?.into_any().unbind()),
            Some(b't') if self.bytes[self.at..].starts_with(b"true") => {
                self.at += 4;
                Ok(true.into_pyobject(self.py)?.to_owned().into_any().unbind())
            }
            Some(b'f') if self.bytes[self.at..].starts_with(b"false") => {
                self.at += 5;
                Ok(false.into_pyobject(self.py)?.to_owned().into_any().unbind())
            }
            Some(b'n') if self.bytes[self.at..].starts_with(b"null") => {
                self.at += 4;
                Ok(self.py.None())
            }
            Some(b'-' | b'0'..=b'9') => self.number(),
            _ => Err(invalid("Malformed JSON scalar")),
        }
    }
}
