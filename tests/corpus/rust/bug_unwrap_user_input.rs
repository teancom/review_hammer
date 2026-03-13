use std::collections::HashMap;

/// Represents a parsed HTTP request.
struct Request {
    headers: HashMap<String, String>,
    body: Vec<u8>,
}

/// Represents a user profile from the database.
struct UserProfile {
    id: u64,
    name: String,
    email: String,
}

/// Handle a user profile update request.
/// BUG: unwrap() on user-controlled input that may be missing or malformed.
fn handle_profile_update(req: &Request) -> Result<UserProfile, String> {
    // BUG: Header may not exist — unwrap() will panic on missing Content-Type
    let content_type = req.headers.get("Content-Type").unwrap();

    if content_type != "application/json" {
        return Err("Invalid content type".to_string());
    }

    // BUG: Body may not be valid UTF-8 — unwrap() will panic on binary input
    let body_str = std::str::from_utf8(&req.body).unwrap();

    // BUG: Body may not be valid JSON — unwrap() will panic on malformed input
    let parsed: serde_json::Value = serde_json::from_str(body_str).unwrap();

    // BUG: Field may not exist or may not be a string — unwrap() will panic
    let name = parsed.get("name").unwrap().as_str().unwrap().to_string();
    let email = parsed.get("email").unwrap().as_str().unwrap().to_string();

    Ok(UserProfile {
        id: 0,
        name,
        email,
    })
}
