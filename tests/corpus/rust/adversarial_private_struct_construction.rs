/// A percentage value that must be between 0.0 and 100.0.
/// The constructor enforces this invariant.
pub struct Percentage {
    value: f64,  // NOTE: private field — not pub
}

impl Percentage {
    /// Create a new Percentage, clamping to valid range.
    pub fn new(value: f64) -> Self {
        Self {
            value: value.clamp(0.0, 100.0),
        }
    }

    pub fn value(&self) -> f64 {
        self.value
    }

    pub fn is_passing(&self) -> bool {
        self.value >= 60.0
    }
}

/// A sorted collection that maintains insertion order invariant.
/// The constructor sorts on creation; methods assume sorted data.
pub struct SortedScores {
    scores: Vec<f64>,  // NOTE: private field — not pub
}

impl SortedScores {
    pub fn new(mut scores: Vec<f64>) -> Self {
        scores.sort_by(|a, b| a.partial_cmp(b).unwrap());
        Self { scores }
    }

    /// Returns the median score. Assumes scores are sorted.
    pub fn median(&self) -> Option<f64> {
        if self.scores.is_empty() {
            return None;
        }
        let mid = self.scores.len() / 2;
        Some(self.scores[mid])
    }

    pub fn percentile(&self, p: f64) -> Option<f64> {
        if self.scores.is_empty() {
            return None;
        }
        let idx = ((p / 100.0) * (self.scores.len() - 1) as f64).round() as usize;
        Some(self.scores[idx])
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_percentage_direct_construction() {
        // BUG: Bypasses constructor invariant — value 150.0 should be clamped to 100.0
        // but direct construction skips the clamp.
        // This test "passes" but tests behavior on invalid state.
        let pct = Percentage { value: 150.0 };
        // This assertion passes with the invalid state, hiding the bug
        assert!(pct.value() > 100.0);
    }

    #[test]
    fn test_sorted_scores_direct_construction() {
        // BUG: Bypasses constructor — scores are NOT sorted.
        // median() assumes sorted data, so it returns wrong value.
        let scores = SortedScores {
            scores: vec![90.0, 10.0, 50.0, 30.0, 70.0],
        };
        // This will return scores[2] = 50.0, which happens to be correct
        // by coincidence, but the data is unsorted so percentile() will be wrong.
        let median = scores.median();
        assert_eq!(median, Some(50.0));
    }

    #[test]
    fn test_percentile_on_unsorted() {
        // BUG: Direct construction with unsorted data breaks percentile calculation
        let scores = SortedScores {
            scores: vec![100.0, 0.0, 50.0],
        };
        // 50th percentile of [0, 50, 100] should be 50, but on unsorted [100, 0, 50]
        // it returns the wrong value
        let p50 = scores.percentile(50.0);
        assert_eq!(p50, Some(0.0)); // "passes" but tests wrong behavior
    }
}
