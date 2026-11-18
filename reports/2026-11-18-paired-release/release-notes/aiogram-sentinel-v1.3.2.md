# aiogram-sentinel 1.3.2

### Native companion and performance

- Prepare the independently installed, exactly matching `aiogram-sentinel-native==1.3.2` ABI 1 companion. Python remains the default; no mandatory native dependency or native extra is added.
- Coarse native rate/debounce entry points preserve handler policies, storage behavior and exact ABI checks.
- Preserve standalone installs and existing optional Redis/navigation integrations.
- Release candidates are not published by CI; publication requires exact artifact, platform and performance qualification and separate approval.



Install this SDK alone for Python operation. Optional Rust operation requires `aiogram-sentinel-native==1.3.2`.
