//! GIL-held data traversal only; Python retains exact JSON number/string formatting.
use pyo3::exceptions::{PyRecursionError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyFloat, PyInt, PyList, PyString, PyTuple, PyType};

fn exact_scalar(value: &Bound<'_, PyAny>) -> bool {
    let py = value.py();
    let ty = value.get_type();
    value.is_none()
        || ty.is(&py.get_type::<PyString>())
        || ty.is(&py.get_type::<PyInt>())
        || ty.is(&py.get_type::<PyBool>())
        || ty.is(&py.get_type::<PyFloat>())
}

#[pyfunction]
#[pyo3(signature=(value, enum_type, mapping_type, fields_fn, datetime_type=None, view_type=None, render_type=None))]
pub fn canonical_value(
    value: &Bound<'_, PyAny>,
    enum_type: &Bound<'_, PyAny>,
    mapping_type: &Bound<'_, PyAny>,
    fields_fn: &Bound<'_, PyAny>,
    datetime_type: Option<&Bound<'_, PyAny>>,
    view_type: Option<&Bound<'_, PyAny>>,
    render_type: Option<&Bound<'_, PyAny>>,
) -> PyResult<Py<PyAny>> {
    canonical_inner(
        value,
        enum_type,
        mapping_type,
        fields_fn,
        datetime_type,
        view_type,
        render_type,
        0,
    )
}

#[allow(clippy::too_many_arguments)]
fn canonical_inner<'py>(
    value: &Bound<'py, PyAny>,
    enum_type: &Bound<'py, PyAny>,
    mapping_type: &Bound<'py, PyAny>,
    fields_fn: &Bound<'py, PyAny>,
    datetime_type: Option<&Bound<'py, PyAny>>,
    view_type: Option<&Bound<'py, PyAny>>,
    render_type: Option<&Bound<'py, PyAny>>,
    depth: usize,
) -> PyResult<Py<PyAny>> {
    if depth > 128 {
        return Err(PyRecursionError::new_err(
            "maximum recursion depth exceeded during canonicalization",
        ));
    }
    let py = value.py();
    if exact_scalar(value) {
        return Ok(value.clone().unbind());
    }
    if let Some(dt) = datetime_type {
        if value.is_instance(dt)? {
            return Ok(value.call_method0("isoformat")?.unbind());
        }
    }
    if value.is_instance(enum_type)? {
        return Ok(value.getattr("value")?.unbind());
    }
    let normalized = if let (Some(view), Some(render)) = (view_type, render_type) {
        if value.is_instance(view)? && value.getattr("render_status")?.eq("complete")? {
            Some(render.call1((
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
    let recur = |child: &Bound<'_, PyAny>| {
        canonical_inner(
            child,
            enum_type,
            mapping_type,
            fields_fn,
            datetime_type,
            view_type,
            render_type,
            depth + 1,
        )
    };
    if !value.is_instance_of::<PyType>() && value.get_type().hasattr("__dataclass_fields__")? {
        let out = PyDict::new(py);
        for field in fields_fn.call1((value,))?.try_iter()? {
            let name = field?.getattr("name")?.extract::<String>()?;
            out.set_item(&name, recur(&value.getattr(name.as_str())?)?)?;
        }
        return Ok(out.into_any().unbind());
    }
    if value.is_instance(mapping_type)? {
        let out = PyDict::new(py);
        for pair in value.call_method0("items")?.try_iter()? {
            let pair = pair?;
            out.set_item(pair.get_item(0)?.str()?, recur(&pair.get_item(1)?)?)?;
        }
        return Ok(out.into_any().unbind());
    }
    if value.is_instance_of::<PyList>() || value.is_instance_of::<PyTuple>() {
        let out = PyList::empty(py);
        for child in value.try_iter()? {
            out.append(recur(&child?)?)?;
        }
        return Ok(out.into_any().unbind());
    }
    Ok(value.clone().unbind())
}

#[pyfunction]
pub fn freeze_value(
    value: &Bound<'_, PyAny>,
    mapping_type: &Bound<'_, PyAny>,
    proxy_type: &Bound<'_, PyAny>,
) -> PyResult<(Py<PyAny>, Py<PyAny>)> {
    freeze(value, mapping_type, proxy_type, 0)
}

fn freeze(
    value: &Bound<'_, PyAny>,
    mapping_type: &Bound<'_, PyAny>,
    proxy_type: &Bound<'_, PyAny>,
    depth: usize,
) -> PyResult<(Py<PyAny>, Py<PyAny>)> {
    let py = value.py();
    if depth > 32 {
        return Err(PyValueError::new_err("JSON nesting exceeds limit"));
    }
    if value.is_instance_of::<PyString>() {
        // Match accepted subclasses' original validation, without changing their data.
        if value.get_type().is(&py.get_type::<PyString>()) {
            value.downcast::<PyString>()?.to_str()?;
        } else {
            value.call_method1("encode", ("utf-8",))?;
        }
        return Ok((value.clone().unbind(), value.clone().unbind()));
    }
    if value.is_none() || value.is_instance_of::<PyBool>() || value.is_instance_of::<PyInt>() {
        return Ok((value.clone().unbind(), value.clone().unbind()));
    }
    if value.is_instance_of::<PyFloat>() {
        if !value.extract::<f64>()?.is_finite() {
            return Err(PyValueError::new_err("JSON numbers must be finite"));
        }
        return Ok((value.clone().unbind(), value.clone().unbind()));
    }
    if value.is_instance(mapping_type)? {
        let frozen = PyDict::new(py);
        let plain = PyDict::new(py);
        for pair in value.call_method0("items")?.try_iter()? {
            let pair = pair?;
            let key = pair.get_item(0)?;
            if !key.is_instance_of::<PyString>() {
                return Err(PyValueError::new_err("JSON keys must be strings"));
            }
            if key.get_type().is(&py.get_type::<PyString>()) {
                key.downcast::<PyString>()?.to_str()?;
            } else {
                key.call_method1("encode", ("utf-8",))?;
            }
            let (a, b) = freeze(&pair.get_item(1)?, mapping_type, proxy_type, depth + 1)?;
            frozen.set_item(&key, a)?;
            plain.set_item(&key, b)?;
        }
        return Ok((
            proxy_type.call1((frozen,))?.unbind(),
            plain.into_any().unbind(),
        ));
    }
    if value.is_instance_of::<PyList>() || value.is_instance_of::<PyTuple>() {
        let mut frozen = Vec::new();
        let plain = PyList::empty(py);
        for child in value.try_iter()? {
            let (a, b) = freeze(&child?, mapping_type, proxy_type, depth + 1)?;
            frozen.push(a);
            plain.append(b)?;
        }
        return Ok((
            PyTuple::new(py, frozen)?.into_any().unbind(),
            plain.into_any().unbind(),
        ));
    }
    Err(PyValueError::new_err("value is not JSON-compatible"))
}
