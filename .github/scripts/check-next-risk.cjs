const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');

const root = path.resolve(process.argv[2]);
const busybox = path.join(root, 'userspace/ksud/bin/x86_64/busybox');
assert.equal(process.platform, 'linux', 'The bundled BusyBox test requires Linux');
assert.equal(process.arch, 'x64', 'The bundled BusyBox test requires x86_64');
fs.chmodSync(busybox, 0o755);
const applets = spawnSync(busybox, ['--list'], { encoding: 'utf8' });
assert.ifError(applets.error);
assert.equal(applets.status, 0, applets.stderr || 'Bundled BusyBox failed');
assert.ok(applets.stdout.split('\n').includes('wget'));
assert.ok(applets.stdout.split('\n').includes('timeout'));
const started = Date.now();
const timeout = spawnSync(busybox, ['timeout', '1', busybox, 'sleep', '30'], { timeout: 5000 });
assert.ok(!timeout.error, 'Bundled BusyBox timeout must stop the subprocess');
assert.notEqual(timeout.status, 0);
assert.ok(Date.now() - started < 5000);
console.log('PASS bundled BusyBox timeout and wget applets');
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'next-risk-host-'));
fs.mkdirSync(path.join(temp, 'src'));
fs.writeFileSync(path.join(temp, 'Cargo.toml'), `[package]
name = "next-risk-host"
version = "0.1.0"
edition = "2024"

[dependencies]
anyhow = "1"
const_format = "0.2"
log = "0.4"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
unicode-normalization = "0.1"
`);
fs.writeFileSync(path.join(temp, 'src/lib.rs'), `
pub mod assets {
    pub const BUSYBOX_PATH: &str = "/bin/false";
}
pub mod defs {
    pub const CACHE_DIR: &str = "/tmp/next-risk-host/";
}
pub mod utils {
    pub fn ensure_dir_exists(_path: &str) -> std::io::Result<()> { Ok(()) }
}
#[path = ${JSON.stringify(path.join(root, 'userspace/ksud/src/risk.rs'))}]
pub mod risk;
#[path = ${JSON.stringify(path.join(root, 'userspace/ksud/src/susfs_response.rs'))}]
pub mod susfs_response;
`);
const locked = spawnSync('cargo', ['generate-lockfile', '--manifest-path', path.join(temp, 'Cargo.toml')],
  { stdio: 'inherit' });
assert.equal(locked.status, 0, 'Host-only test harness dependency lock generation failed');
const result = spawnSync('cargo', [
  'test', '--locked', '--manifest-path', path.join(temp, 'Cargo.toml'), '--lib',
  '--', '--nocapture', '--test-threads=1',
], { stdio: 'inherit', env: { ...process.env, CARGO_TARGET_DIR: path.join(temp, 'target') } });
if (result.error) console.error(result.error.message);
process.exit(result.status ?? 1);
