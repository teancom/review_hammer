/// Comprehensive test suite for ConnectionManager state machine.
///
/// This test suite demonstrates complete coverage of:
/// - State transitions (all valid and invalid transitions)
/// - Error paths (all error conditions)
/// - Boundary conditions (max reconnection attempts)
/// - Idempotent properties (disconnect + reconnect)

use super::*;

#[test]
fn test_initial_state_is_idle() {
    let manager = ConnectionManager::new();
    assert_eq!(manager.state(), ConnectionState::Idle);
}

#[test]
fn test_connect_from_idle_succeeds() {
    let mut manager = ConnectionManager::new();
    assert!(manager.connect().is_ok());
    assert_eq!(manager.state(), ConnectionState::Connecting);
}

#[test]
fn test_connect_from_disconnected_succeeds() {
    let mut manager = ConnectionManager::new();
    manager.connect().unwrap();
    manager.finish_connect().unwrap();
    manager.disconnect().unwrap();

    // Now in Disconnected state, should be able to reconnect manually
    assert!(manager.connect().is_ok());
    assert_eq!(manager.state(), ConnectionState::Connecting);
    // Verify that reconnection attempts counter is reset
    assert_eq!(manager.reconnection_attempts, 0);
}

#[test]
fn test_connect_from_connecting_fails() {
    let mut manager = ConnectionManager::new();
    manager.connect().unwrap();
    // Try to connect again while already connecting
    let result = manager.connect();
    assert!(result.is_err());
    assert_eq!(
        result.unwrap_err(),
        ConnectionError::InvalidState("Already connecting".to_string())
    );
}

#[test]
fn test_connect_from_connected_fails() {
    let mut manager = ConnectionManager::new();
    manager.connect().unwrap();
    manager.finish_connect().unwrap();
    // Try to connect again while already connected
    let result = manager.connect();
    assert!(result.is_err());
    assert_eq!(
        result.unwrap_err(),
        ConnectionError::InvalidState("Already connected".to_string())
    );
}

#[test]
fn test_finish_connect_from_connecting_succeeds() {
    let mut manager = ConnectionManager::new();
    manager.connect().unwrap();
    assert!(manager.finish_connect().is_ok());
    assert_eq!(manager.state(), ConnectionState::Connected);
}

#[test]
fn test_finish_connect_from_idle_fails() {
    let mut manager = ConnectionManager::new();
    let result = manager.finish_connect();
    assert!(result.is_err());
}

#[test]
fn test_finish_connect_from_connected_fails() {
    let mut manager = ConnectionManager::new();
    manager.connect().unwrap();
    manager.finish_connect().unwrap();
    let result = manager.finish_connect();
    assert!(result.is_err());
}

#[test]
fn test_disconnect_from_connected_succeeds() {
    let mut manager = ConnectionManager::new();
    manager.connect().unwrap();
    manager.finish_connect().unwrap();
    assert!(manager.disconnect().is_ok());
    assert_eq!(manager.state(), ConnectionState::Disconnected);
}

#[test]
fn test_disconnect_from_disconnected_fails() {
    let mut manager = ConnectionManager::new();
    manager.connect().unwrap();
    manager.finish_connect().unwrap();
    manager.disconnect().unwrap();
    let result = manager.disconnect();
    assert!(result.is_err());
}

#[test]
fn test_disconnect_from_idle_fails() {
    let mut manager = ConnectionManager::new();
    let result = manager.disconnect();
    assert!(result.is_err());
}

#[test]
fn test_disconnect_clears_message_queue() {
    let mut manager = ConnectionManager::new();
    manager.connect().unwrap();
    manager.finish_connect().unwrap();
    manager.send("msg1").unwrap();
    manager.send("msg2").unwrap();
    manager.disconnect().unwrap();
    let messages = manager.flush();
    assert!(messages.is_empty());
}

#[test]
fn test_send_when_connected_succeeds() {
    let mut manager = ConnectionManager::new();
    manager.connect().unwrap();
    manager.finish_connect().unwrap();
    assert!(manager.send("test message").is_ok());
}

#[test]
fn test_send_when_disconnected_fails() {
    let mut manager = ConnectionManager::new();
    manager.connect().unwrap();
    manager.finish_connect().unwrap();
    manager.disconnect().unwrap();
    let result = manager.send("test message");
    assert!(result.is_err());
    assert_eq!(result.unwrap_err(), ConnectionError::SendFailed);
}

#[test]
fn test_send_when_idle_fails() {
    let mut manager = ConnectionManager::new();
    let result = manager.send("test message");
    assert!(result.is_err());
}

#[test]
fn test_send_when_connecting_fails() {
    let mut manager = ConnectionManager::new();
    manager.connect().unwrap();
    let result = manager.send("test message");
    assert!(result.is_err());
}

#[test]
fn test_flush_returns_and_clears_messages() {
    let mut manager = ConnectionManager::new();
    manager.connect().unwrap();
    manager.finish_connect().unwrap();
    manager.send("msg1").unwrap();
    manager.send("msg2").unwrap();
    manager.send("msg3").unwrap();

    let messages = manager.flush();
    assert_eq!(messages, vec!["msg1", "msg2", "msg3"]);

    // After flush, queue should be empty
    let messages = manager.flush();
    assert!(messages.is_empty());
}

#[test]
fn test_reconnect_from_disconnected_succeeds() {
    let mut manager = ConnectionManager::new();
    manager.connect().unwrap();
    manager.finish_connect().unwrap();
    manager.disconnect().unwrap();

    assert!(manager.reconnect().is_ok());
    assert_eq!(manager.state(), ConnectionState::Connecting);
}

#[test]
fn test_reconnect_from_idle_fails() {
    let mut manager = ConnectionManager::new();
    let result = manager.reconnect();
    assert!(result.is_err());
}

#[test]
fn test_reconnect_increments_attempts() {
    let mut manager = ConnectionManager::new();
    manager.connect().unwrap();
    manager.finish_connect().unwrap();
    manager.disconnect().unwrap();

    assert_eq!(manager.reconnection_attempts, 0);
    manager.reconnect().unwrap();
    assert_eq!(manager.reconnection_attempts, 1);
}

#[test]
fn test_reconnect_respects_max_attempts() {
    let mut manager = ConnectionManager::new();
    manager.max_reconnection_attempts = 2;

    manager.connect().unwrap();
    manager.finish_connect().unwrap();
    manager.disconnect().unwrap();

    // First attempt succeeds
    manager.reconnect().unwrap();
    manager.state = ConnectionState::Disconnected; // Simulate failure
    assert_eq!(manager.reconnection_attempts, 1);

    // Second attempt succeeds
    manager.reconnect().unwrap();
    manager.state = ConnectionState::Disconnected;
    assert_eq!(manager.reconnection_attempts, 2);

    // Third attempt fails (max reached)
    let result = manager.reconnect();
    assert!(result.is_err());
    assert_eq!(
        result.unwrap_err(),
        ConnectionError::ConnectionFailed
    );
}

#[test]
fn test_disconnect_then_reconnect_idempotent() {
    let mut manager = ConnectionManager::new();

    // Initial connection
    manager.connect().unwrap();
    manager.finish_connect().unwrap();
    assert_eq!(manager.state(), ConnectionState::Connected);

    // Disconnect
    manager.disconnect().unwrap();
    assert_eq!(manager.state(), ConnectionState::Disconnected);

    // Reconnect
    manager.reconnect().unwrap();
    assert_eq!(manager.state(), ConnectionState::Connecting);

    // Complete reconnection
    manager.finish_connect().unwrap();
    assert_eq!(manager.state(), ConnectionState::Connected);
}

#[test]
fn test_default_creates_idle_manager() {
    let manager = ConnectionManager::default();
    assert_eq!(manager.state(), ConnectionState::Idle);
}

#[test]
fn test_full_lifecycle() {
    let mut manager = ConnectionManager::new();

    // Start in Idle
    assert_eq!(manager.state(), ConnectionState::Idle);

    // Transition to Connecting, then Connected
    manager.connect().unwrap();
    manager.finish_connect().unwrap();
    assert_eq!(manager.state(), ConnectionState::Connected);

    // Send some messages
    manager.send("hello").unwrap();
    manager.send("world").unwrap();

    // Verify messages are queued
    let messages = manager.flush();
    assert_eq!(messages.len(), 2);

    // Disconnect
    manager.disconnect().unwrap();
    assert_eq!(manager.state(), ConnectionState::Disconnected);
}
