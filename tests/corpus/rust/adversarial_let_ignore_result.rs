use std::fs::File;
use std::io::Write;

/// Represents a financial transaction record.
struct Transaction {
    id: u64,
    amount_cents: i64,
    description: String,
}

/// Write a transaction to the audit log.
/// BUG: Silently discards write errors — audit data may be lost without detection.
/// This uses `let _ =` like fire-and-forget channel sends, but here the result is critical.
fn log_transaction(file: &mut File, txn: &Transaction) {
    let record = format!(
        "{},{},{}\n",
        txn.id, txn.amount_cents, txn.description
    );

    // BUG: `let _ = file.write()` silently discards I/O errors.
    // Unlike fire-and-forget channel sends, file write failures mean audit data is LOST.
    // Disk full, permission denied, broken pipe — all silently ignored.
    let _ = file.write_all(record.as_bytes());
}

/// Process a batch of transactions.
/// BUG: If any write fails, the function continues silently — partial audit logs with no error.
fn process_batch(transactions: Vec<Transaction>, log_path: &str) {
    let mut file = File::create(log_path).expect("failed to open audit log");

    for txn in &transactions {
        // BUG: Each write error is silently discarded via `let _ =`
        log_transaction(&mut file, txn);
    }

    // BUG: fsync result also discarded — data may not be persisted
    let _ = file.sync_all();
}
