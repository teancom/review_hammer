use std::thread;

/// Global counter with no synchronization.
/// BUG: Mutable static accessed from multiple threads causes data races.
static mut REQUEST_COUNT: u64 = 0;

/// Increment the global request counter.
/// BUG: This is unsound — concurrent access to mutable static is undefined behavior.
fn increment_counter() {
    unsafe {
        REQUEST_COUNT += 1;
    }
}

/// Get the current request count.
fn get_counter() -> u64 {
    unsafe { REQUEST_COUNT }
}

/// Simulate a server handling concurrent requests.
/// BUG: Multiple threads mutate REQUEST_COUNT without any synchronization primitive.
fn run_server() {
    let mut handles = vec![];

    for _ in 0..10 {
        let handle = thread::spawn(|| {
            for _ in 0..1000 {
                // BUG: Data race — multiple threads writing to static mut
                increment_counter();
            }
        });
        handles.push(handle);
    }

    for handle in handles {
        handle.join().unwrap();
    }

    // Value is likely incorrect due to data races
    println!("Total requests: {}", get_counter());
}
