/// A sample rate newtype with transparent representation.
/// Direct construction (e.g., `SampleRate(44100)`) is the public API.
#[repr(transparent)]
pub struct SampleRate(pub u32);

impl SampleRate {
    pub fn as_hz(&self) -> u32 {
        self.0
    }
}

/// Audio buffer size in frames.
#[repr(transparent)]
pub struct BufferSize(pub usize);

impl BufferSize {
    pub fn byte_count(&self, channels: usize, bit_depth: usize) -> usize {
        self.0 * channels * (bit_depth / 8)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sample_rate_construction() {
        // Direct construction of #[repr(transparent)] tuple struct — this IS the public API.
        let rate = SampleRate(44100);
        assert_eq!(rate.as_hz(), 44100);
    }

    #[test]
    fn test_standard_rates() {
        let rates = [SampleRate(22050), SampleRate(44100), SampleRate(48000), SampleRate(96000)];
        for rate in &rates {
            assert!(rate.as_hz() > 0);
        }
    }

    #[test]
    fn test_buffer_size_byte_count() {
        let buf = BufferSize(512);
        // stereo 16-bit: 512 frames * 2 channels * 2 bytes = 2048
        assert_eq!(buf.byte_count(2, 16), 2048);
    }
}
