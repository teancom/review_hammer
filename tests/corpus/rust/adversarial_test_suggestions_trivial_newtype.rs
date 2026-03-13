//! Newtype wrappers and trivial data structures.
//!
//! This file contains pure data types with derived traits and simple accessors.
//! The code is too trivial to warrant any meaningful test suggestions.

use std::fmt;

/// A user ID newtype wrapper.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct UserId(u64);

impl UserId {
    /// Create a UserId from a raw u64.
    pub fn new(id: u64) -> Self {
        UserId(id)
    }

    /// Get the inner u64 value.
    pub fn inner(&self) -> u64 {
        self.0
    }
}

impl From<u64> for UserId {
    fn from(id: u64) -> Self {
        UserId(id)
    }
}

impl fmt::Display for UserId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "UserId({})", self.0)
    }
}

impl Default for UserId {
    fn default() -> Self {
        UserId(0)
    }
}

/// An email address newtype wrapper.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct Email(String);

impl Email {
    /// Create an Email from a string.
    pub fn new(email: String) -> Self {
        Email(email)
    }

    /// Get the email as a string slice.
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl From<String> for Email {
    fn from(email: String) -> Self {
        Email(email)
    }
}

impl From<&str> for Email {
    fn from(email: &str) -> Self {
        Email(email.to_string())
    }
}

impl fmt::Display for Email {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl Default for Email {
    fn default() -> Self {
        Email(String::new())
    }
}

/// A simple user record containing pure data.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UserRecord {
    /// The user's ID
    pub id: UserId,
    /// The user's email address
    pub email: Email,
    /// Unix timestamp when the user was created
    pub created_at: u64,
}

impl UserRecord {
    /// Create a new UserRecord.
    pub fn new(id: UserId, email: Email, created_at: u64) -> Self {
        UserRecord {
            id,
            email,
            created_at,
        }
    }
}

impl Default for UserRecord {
    fn default() -> Self {
        UserRecord {
            id: UserId::default(),
            email: Email::default(),
            created_at: 0,
        }
    }
}

/// A simple session token wrapper.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SessionToken(u128);

impl SessionToken {
    /// Create a new session token.
    pub fn new(token: u128) -> Self {
        SessionToken(token)
    }

    /// Get the inner token value.
    pub fn token(&self) -> u128 {
        self.0
    }
}

impl Default for SessionToken {
    fn default() -> Self {
        SessionToken(0)
    }
}

/// A request ID newtype for tracing.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct RequestId(u64);

impl RequestId {
    /// Create a new RequestId.
    pub fn new(id: u64) -> Self {
        RequestId(id)
    }

    /// Get the inner ID.
    pub fn id(&self) -> u64 {
        self.0
    }
}

impl fmt::Display for RequestId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}
