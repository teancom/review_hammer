//! Configuration file parser with error handling but no tests.
//!
//! This module implements a simple configuration file parser that handles
//! multiple sections and key-value pairs. It has error handling paths but
//! NO tests exist, creating multiple test coverage gaps.

use std::collections::HashMap;

/// Represents a parsing error.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ParseError {
    /// Encountered a duplicate key in the same section
    DuplicateKey { section: String, key: String },
    /// A required section is missing
    MissingSection { section: String },
    /// Invalid value format for a configuration option
    InvalidValue { section: String, key: String, reason: String },
    /// Unexpected end of input
    UnexpectedEof,
}

/// Configuration structure after parsing.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Config {
    sections: HashMap<String, HashMap<String, String>>,
}

impl Config {
    /// Get a value from a section.
    pub fn get(&self, section: &str, key: &str) -> Option<&str> {
        self.sections
            .get(section)
            .and_then(|s| s.get(key))
            .map(|v| v.as_str())
    }

    /// List all sections in the config.
    pub fn sections(&self) -> Vec<&str> {
        self.sections.keys().map(|s| s.as_str()).collect()
    }

    /// Get all keys in a section.
    pub fn keys(&self, section: &str) -> Vec<&str> {
        self.sections
            .get(section)
            .map(|s| s.keys().map(|k| k.as_str()).collect())
            .unwrap_or_default()
    }
}

/// Parse a configuration string into a Config structure.
///
/// Format:
/// ```
/// [section1]
/// key1=value1
/// key2=value2
///
/// [section2]
/// key3=value3
/// ```
///
/// Constraints:
/// - Each section must start with `[section_name]` on its own line
/// - Key-value pairs must be in format `key=value`
/// - Duplicate keys in the same section are an error
/// - Empty lines are ignored
/// - Lines starting with # are comments
pub fn parse_config(input: &str) -> Result<Config, ParseError> {
    let mut sections = HashMap::new();
    let mut current_section = String::new();
    let mut lines = input.lines().peekable();

    while let Some(line) = lines.next() {
        let trimmed = line.trim();

        // Skip empty lines and comments
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }

        // Check if this is a section header
        if trimmed.starts_with('[') && trimmed.ends_with(']') {
            current_section = trimmed[1..trimmed.len() - 1].to_string();
            sections.insert(current_section.clone(), HashMap::new());
            continue;
        }

        // This should be a key=value pair
        if current_section.is_empty() {
            return Err(ParseError::UnexpectedEof);
        }

        let (key, value) = parse_key_value(trimmed)?;

        // Check for duplicate key
        let section_map = sections
            .get_mut(&current_section)
            .ok_or_else(|| ParseError::MissingSection {
                section: current_section.clone(),
            })?;

        if section_map.contains_key(key) {
            return Err(ParseError::DuplicateKey {
                section: current_section.clone(),
                key: key.to_string(),
            });
        }

        section_map.insert(key.to_string(), value.to_string());
    }

    Ok(Config { sections })
}

/// Parse a single key=value pair from a line.
fn parse_key_value(line: &str) -> Result<(&str, &str), ParseError> {
    let parts: Vec<&str> = line.splitn(2, '=').collect();
    if parts.len() != 2 {
        return Err(ParseError::InvalidValue {
            section: String::new(),
            key: String::new(),
            reason: "Expected key=value format".to_string(),
        });
    }

    let key = parts[0].trim();
    let value = parts[1].trim();

    // Validate key is not empty
    if key.is_empty() {
        return Err(ParseError::InvalidValue {
            section: String::new(),
            key: String::new(),
            reason: "Key cannot be empty".to_string(),
        });
    }

    // Validate value constraints based on key prefix
    if key.starts_with("max_") && !value.parse::<u32>().is_ok() {
        return Err(ParseError::InvalidValue {
            section: String::new(),
            key: key.to_string(),
            reason: "Expected numeric value".to_string(),
        });
    }

    Ok((key, value))
}

/// Parse config with strict validation of required sections.
pub fn parse_config_strict(input: &str, required_sections: &[&str]) -> Result<Config, ParseError> {
    let config = parse_config(input)?;

    // Verify all required sections exist
    for required in required_sections {
        if !config.sections.contains_key(*required) {
            return Err(ParseError::MissingSection {
                section: required.to_string(),
            });
        }
    }

    Ok(config)
}
