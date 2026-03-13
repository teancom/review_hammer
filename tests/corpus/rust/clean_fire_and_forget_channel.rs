use tokio::sync::mpsc;

struct StatusUpdate {
    message: String,
    timestamp: u64,
}

/// Background task that periodically sends status updates.
/// The receiver may drop during shutdown — discarding the send result is intentional.
async fn status_reporter(tx: mpsc::Sender<StatusUpdate>) {
    loop {
        let update = StatusUpdate {
            message: "heartbeat".to_string(),
            timestamp: current_timestamp(),
        };

        // Fire-and-forget: receiver may have dropped during shutdown.
        // This is intentional — we don't want to abort the loop on send failure.
        let _ = tx.send(update).await;

        tokio::time::sleep(std::time::Duration::from_secs(30)).await;
    }
}

/// Spawned background task for logging events to a channel.
/// The monitoring system may shut down before this task completes.
fn spawn_event_logger(tx: mpsc::UnboundedSender<String>) {
    tokio::spawn(async move {
        for event in collect_events().await {
            // Fire-and-forget: if the event consumer is gone, silently discard.
            let _ = tx.send(event);
        }
    });
}

// Stub functions for syntactic validity
fn current_timestamp() -> u64 { 0 }
async fn collect_events() -> Vec<String> { vec![] }
