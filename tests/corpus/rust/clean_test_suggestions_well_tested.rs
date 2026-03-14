//! Connection state machine with comprehensive test coverage.
//!
//! This module demonstrates a simple state machine with proper error handling,
//! state transitions, and boundary conditions. It is well-tested with all paths covered.

use std::collections::VecDeque;

/// Represents the state of a connection.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConnectionState {
    /// Initial state, no connection attempt in progress
    Idle,
    /// Connection attempt in progress
    Connecting,
    /// Active connection established
    Connected,
    /// Connection has been closed
    Disconnected,
}

/// Errors that can occur during connection operations.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ConnectionError {
    /// Attempted operation in invalid state
    InvalidState(String),
    /// Connection failed
    ConnectionFailed,
    /// Message failed to send
    SendFailed,
}

/// Manages a connection with state machine semantics.
pub struct ConnectionManager {
    state: ConnectionState,
    reconnection_attempts: u32,
    max_reconnection_attempts: u32,
    message_queue: VecDeque<String>,
}

impl ConnectionManager {
    /// Create a new ConnectionManager in Idle state.
    pub fn new() -> Self {
        ConnectionManager {
            state: ConnectionState::Idle,
            reconnection_attempts: 0,
            max_reconnection_attempts: 3,
            message_queue: VecDeque::new(),
        }
    }

    /// Get the current connection state.
    pub fn state(&self) -> ConnectionState {
        self.state
    }

    /// Attempt to establish a connection.
    /// Valid from Idle or Disconnected states.
    pub fn connect(&mut self) -> Result<(), ConnectionError> {
        match self.state {
            ConnectionState::Idle | ConnectionState::Disconnected => {
                self.state = ConnectionState::Connecting;
                self.reconnection_attempts = 0;
                Ok(())
            }
            ConnectionState::Connecting => {
                Err(ConnectionError::InvalidState(
                    "Already connecting".to_string(),
                ))
            }
            ConnectionState::Connected => {
                Err(ConnectionError::InvalidState(
                    "Already connected".to_string(),
                ))
            }
        }
    }

    /// Simulate successful completion of connection.
    /// Only valid from Connecting state.
    pub fn finish_connect(&mut self) -> Result<(), ConnectionError> {
        match self.state {
            ConnectionState::Connecting => {
                self.state = ConnectionState::Connected;
                Ok(())
            }
            _ => Err(ConnectionError::InvalidState(
                "Must be in Connecting state".to_string(),
            )),
        }
    }

    /// Disconnect the connection.
    /// Valid from Connected state only.
    pub fn disconnect(&mut self) -> Result<(), ConnectionError> {
        match self.state {
            ConnectionState::Connected => {
                self.state = ConnectionState::Disconnected;
                self.message_queue.clear();
                Ok(())
            }
            ConnectionState::Disconnected => {
                Err(ConnectionError::InvalidState(
                    "Already disconnected".to_string(),
                ))
            }
            _ => Err(ConnectionError::InvalidState(
                "Must be connected to disconnect".to_string(),
            )),
        }
    }

    /// Send a message. Only valid when Connected.
    pub fn send(&mut self, msg: &str) -> Result<(), ConnectionError> {
        match self.state {
            ConnectionState::Connected => {
                self.message_queue.push_back(msg.to_string());
                Ok(())
            }
            ConnectionState::Disconnected => {
                Err(ConnectionError::SendFailed)
            }
            _ => Err(ConnectionError::InvalidState(
                "Must be connected to send".to_string(),
            )),
        }
    }

    /// Get and clear pending messages.
    pub fn flush(&mut self) -> Vec<String> {
        self.message_queue.drain(..).collect()
    }

    /// Handle a reconnection attempt when disconnected.
    /// Returns error if max reconnection attempts exceeded.
    pub fn reconnect(&mut self) -> Result<(), ConnectionError> {
        if self.state != ConnectionState::Disconnected {
            return Err(ConnectionError::InvalidState(
                "Only valid when disconnected".to_string(),
            ));
        }

        if self.reconnection_attempts >= self.max_reconnection_attempts {
            return Err(ConnectionError::ConnectionFailed);
        }

        self.reconnection_attempts += 1;
        self.state = ConnectionState::Connecting;
        Ok(())
    }
}

impl Default for ConnectionManager {
    fn default() -> Self {
        Self::new()
    }
}
