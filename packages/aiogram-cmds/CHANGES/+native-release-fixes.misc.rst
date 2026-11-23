Borrow resolved command strings at the native hashing boundary rather than
copying every command and description into Rust-owned strings. Keep
canonical fingerprints and uncached live translation behavior unchanged.
