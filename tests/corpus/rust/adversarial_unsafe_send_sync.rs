use std::ptr;

/// A connection pool that manages raw pointers to database connections.
/// BUG: This is NOT a COM object — no runtime provides internal synchronization.
pub struct ConnectionPool {
    connections: *mut Vec<*mut u8>,
    active_count: usize,
}

// BUG: unsafe impl Send + Sync without any synchronization mechanism.
// Unlike COM MTA objects, this type has no runtime providing thread safety.
// Multiple threads can concurrently:
// - Read/write active_count (data race)
// - Dereference and mutate the connections Vec (use-after-free, double-free)
// - Push/pop connections while another thread iterates (UB)
unsafe impl Send for ConnectionPool {}
unsafe impl Sync for ConnectionPool {}

impl ConnectionPool {
    pub fn new(capacity: usize) -> Self {
        let connections = Box::into_raw(Box::new(Vec::with_capacity(capacity)));
        Self {
            connections,
            active_count: 0,
        }
    }

    /// Get a connection from the pool.
    /// BUG: No locking — concurrent calls cause data races on active_count and connections.
    pub fn acquire(&mut self) -> Option<*mut u8> {
        let conns = unsafe { &mut *self.connections };
        if let Some(conn) = conns.pop() {
            self.active_count += 1;
            Some(conn)
        } else {
            None
        }
    }

    /// Return a connection to the pool.
    /// BUG: No locking — concurrent returns cause data races.
    pub fn release(&mut self, conn: *mut u8) {
        let conns = unsafe { &mut *self.connections };
        conns.push(conn);
        self.active_count -= 1;
    }
}

impl Drop for ConnectionPool {
    fn drop(&mut self) {
        let conns = unsafe { Box::from_raw(self.connections) };
        for conn in conns.iter() {
            unsafe { drop(Box::from_raw(*conn)) };
        }
    }
}
