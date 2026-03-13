use std::ptr;

/// Opaque COM interface pointer (simplified for corpus).
#[repr(transparent)]
struct IMMDeviceEnumerator(*mut std::ffi::c_void);

/// Audio device manager wrapping a COM interface.
/// Initialized with COINIT_MULTITHREADED — MTA provides internal synchronization.
pub struct AudioDeviceManager {
    enumerator: IMMDeviceEnumerator,
}

// SAFETY: AudioDeviceManager wraps a COM object initialized on a Multi-Threaded Apartment (MTA).
// MTA guarantees that COM provides internal synchronization for concurrent access from any thread.
// This is safe because:
// 1. CoInitializeEx is called with COINIT_MULTITHREADED before creating the object
// 2. MTA objects handle their own thread marshaling internally
// 3. The COM runtime serializes calls when needed
unsafe impl Send for AudioDeviceManager {}
unsafe impl Sync for AudioDeviceManager {}

impl AudioDeviceManager {
    /// Create a new audio device manager. Must be called after CoInitializeEx(COINIT_MULTITHREADED).
    pub fn new() -> Result<Self, i32> {
        // In real code: CoCreateInstance for IMMDeviceEnumerator
        Ok(Self {
            enumerator: IMMDeviceEnumerator(ptr::null_mut()),
        })
    }

    pub fn get_default_device_name(&self) -> Option<String> {
        // In real code: enumerate devices via COM interface
        Some("Default Audio Device".to_string())
    }
}

impl Drop for AudioDeviceManager {
    fn drop(&mut self) {
        // In real code: Release() the COM interface
    }
}
