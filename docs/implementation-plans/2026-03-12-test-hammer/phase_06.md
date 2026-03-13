# Test Hammer Implementation Plan — Phase 6: Additional Language Prompts

**Goal:** Add `## test-suggestions` sections to the remaining 10 language prompt templates (python, go, typescript, javascript, java, kotlin, swift, cpp, c, csharp).

**Architecture:** Each language prompt file gets a `## test-suggestions` section appended after the last existing section (which will be `## brittle-tests` after Phase 5 removes `## missing-edge-cases`). Each section follows the same structure as the rust.md and generic.md sections created in Phase 1, but with language-specific DO NOT SUGGEST exclusion lists.

**Dependency:** This phase MUST run after Phase 5 (Review-Hammer Integration), which removes `## missing-edge-cases` from all prompt files. Without Phase 5 complete, the "last section" in each file would be `## missing-edge-cases`, not `## brittle-tests`, and the insertion point would be wrong.

**Tech Stack:** Markdown prompt templates

**Scope:** 6 phases from original design (this is phase 6 of 6)

**Codebase verified:** 2026-03-13

---

## Acceptance Criteria Coverage

This phase implements and tests:

### test-hammer.AC3: Language-specific prompt templates
- **test-hammer.AC3.4 Success:** All 12 language prompt files contain `## test-suggestions` sections with language-appropriate exclusion lists

---

<!-- START_TASK_1 -->
### Task 1: Add `## test-suggestions` to `prompts/python.md`

**Verifies:** test-hammer.AC3.4

**Files:**
- Modify: `prompts/python.md` (append after the last section, `## brittle-tests` after Phase 5 removes `## missing-edge-cases`)

**Implementation:**

Append the following `## test-suggestions` section. The WHAT TO SUGGEST list is the same as generic.md. The DO NOT SUGGEST list includes Python-specific exclusions:

```markdown

---

## test-suggestions

You are now a test-suggestion specialist. Given production source code and optionally existing test code, suggest up to **3** high-value tests that are missing.

**Output format:** Same JSON array as other categories. In the `description` field, explain WHAT to test and WHY it matters — not how to implement the test. The `category` field must be `"test-suggestions"`.

**IMPORTANT:** Return at most 3 suggestions. If fewer than 3 are warranted, return fewer. If nothing is worth suggesting, return `[]`.

**WHAT TO SUGGEST** (in priority order):

1. **State transition coverage** — Code with distinct states where transitions between states are not tested. Focus on transitions that change observable behavior.
2. **Error path coverage** — Error handling paths (try/except, custom exceptions, error returns) with no corresponding error-case tests. Prioritize paths where the error transforms data or has side effects.
3. **Business logic boundaries** — Domain-specific boundary conditions where behavior changes (thresholds, limits, mode switches). The boundary must be in THIS code, not in a called function.
4. **Integration seam tests** — Boundaries between components where one side makes assumptions about the other's behavior (protocol classes, callback contracts, message formats). Focus on assumptions that could silently diverge.
5. **Property-based test opportunities** — Functions with clear invariants: roundtrip encode/decode, idempotency, commutativity. Only suggest when the invariant is non-trivial and not already covered.

**DO NOT SUGGEST:**

- Tests that validate Python language semantics (None is falsy, empty list is falsy, dict keys are unique)
- Tests that duplicate what type checkers (mypy/pyright) enforce
- Tests for trivial `__init__` assignment (`self.x = x`)
- Tests for dataclass/attrs/pydantic default values or field types
- Tests for trivial properties/getters/setters with no logic
- Tests that merely exercise code for coverage without meaningful assertions
- Tests for `__repr__`/`__str__` output formatting on simple classes
- Tests for framework-provided behavior (Django ORM basic CRUD, Flask routing)
- Tests for pure data structures with no logic (TypedDict, NamedTuple with no methods)
- Tests already covered in the existing test file(s) provided as context
- Tests that only verify a function "doesn't raise" without checking the result
```

**Verification:**

```bash
grep -c '## test-suggestions' prompts/python.md
```
Expected: `1`

**Commit:** `feat: add test-suggestions to python.md prompt`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add `## test-suggestions` to `prompts/go.md`

**Verifies:** test-hammer.AC3.4

**Files:**
- Modify: `prompts/go.md` (append after `## brittle-tests`)

**Implementation:**

Append `## test-suggestions` with Go-specific DO NOT SUGGEST list:

```markdown

---

## test-suggestions

You are now a test-suggestion specialist. Given production source code and optionally existing test code, suggest up to **3** high-value tests that are missing.

**Output format:** Same JSON array as other categories. In the `description` field, explain WHAT to test and WHY it matters — not how to implement the test. The `category` field must be `"test-suggestions"`.

**IMPORTANT:** Return at most 3 suggestions. If fewer than 3 are warranted, return fewer. If nothing is worth suggesting, return `[]`.

**WHAT TO SUGGEST** (in priority order):

1. **State transition coverage** — Code with distinct states where transitions between states are not tested. Focus on transitions that change observable behavior.
2. **Error path coverage** — Error handling paths (error returns, sentinel errors, wrapped errors) with no corresponding error-case tests. Prioritize paths where the error transforms data or has side effects.
3. **Business logic boundaries** — Domain-specific boundary conditions where behavior changes (thresholds, limits, mode switches). The boundary must be in THIS code, not in a called function.
4. **Integration seam tests** — Boundaries between components where one side makes assumptions about the other's behavior (interface implementations, callback contracts, message formats). Focus on assumptions that could silently diverge.
5. **Property-based test opportunities** — Functions with clear invariants: roundtrip encode/decode, idempotency, commutativity. Only suggest when the invariant is non-trivial and not already covered.

**DO NOT SUGGEST:**

- Tests that validate Go language semantics (nil slice is valid, zero values are usable, channels block)
- Tests for `errors.Is`/`errors.As` on standard error types
- Tests for interface satisfaction (compiler checks this)
- Tests for trivial struct field access with no logic
- Tests for `String()` methods on simple types
- Tests that merely exercise code for coverage without meaningful assertions
- Tests for `json.Marshal`/`json.Unmarshal` on simple structs with standard tags
- Tests for framework-provided behavior (net/http handler registration, standard middleware)
- Tests for pure data structures with no methods
- Tests already covered in the existing test file(s) provided as context
- Tests that only verify a function "doesn't panic" without checking the result
```

**Verification:**

```bash
grep -c '## test-suggestions' prompts/go.md
```
Expected: `1`

**Commit:** `feat: add test-suggestions to go.md prompt`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add `## test-suggestions` to `prompts/typescript.md` and `prompts/javascript.md`

**Verifies:** test-hammer.AC3.4

**Files:**
- Modify: `prompts/typescript.md` (append after `## brittle-tests`)
- Modify: `prompts/javascript.md` (append after `## brittle-tests`)

**Implementation:**

Both TypeScript and JavaScript share very similar patterns. Add `## test-suggestions` with TS/JS-specific DO NOT SUGGEST lists.

**For typescript.md:**

```markdown

---

## test-suggestions

You are now a test-suggestion specialist. Given production source code and optionally existing test code, suggest up to **3** high-value tests that are missing.

**Output format:** Same JSON array as other categories. In the `description` field, explain WHAT to test and WHY it matters — not how to implement the test. The `category` field must be `"test-suggestions"`.

**IMPORTANT:** Return at most 3 suggestions. If fewer than 3 are warranted, return fewer. If nothing is worth suggesting, return `[]`.

**WHAT TO SUGGEST** (in priority order):

1. **State transition coverage** — Code with distinct states where transitions between states are not tested. Focus on transitions that change observable behavior.
2. **Error path coverage** — Error handling paths (try/catch, Promise rejection, error callbacks) with no corresponding error-case tests. Prioritize paths where the error transforms data or has side effects.
3. **Business logic boundaries** — Domain-specific boundary conditions where behavior changes (thresholds, limits, mode switches). The boundary must be in THIS code, not in a called function.
4. **Integration seam tests** — Boundaries between components where one side makes assumptions about the other's behavior (interface contracts, callback signatures, event payloads). Focus on assumptions that could silently diverge.
5. **Property-based test opportunities** — Functions with clear invariants: roundtrip encode/decode, idempotency, commutativity. Only suggest when the invariant is non-trivial and not already covered.

**DO NOT SUGGEST:**

- Tests that validate TypeScript type system behavior (type narrowing, union discrimination, generic constraints)
- Tests for type guards that the compiler already verifies
- Tests for trivial getters/setters/accessors with no logic
- Tests for interface/type definitions (compiler checks these)
- Tests that merely exercise code for coverage without meaningful assertions
- Tests for React component rendering with no logic (pure presentational components)
- Tests for framework-provided behavior (Express routing, Next.js data fetching patterns)
- Tests for pure data structures or type definitions with no methods
- Tests already covered in the existing test file(s) provided as context
- Tests that only verify a function "doesn't throw" without checking the result
```

**For javascript.md:** Same content but replace "TypeScript type system behavior (type narrowing, union discrimination, generic constraints)" with "JavaScript language semantics (undefined vs null, truthy/falsy coercion, prototype chain)" and remove the TypeScript-specific items (type guards, interface/type definitions). Replace with:

```
- Tests that validate JavaScript language semantics (undefined vs null, truthy/falsy coercion, prototype chain)
- Tests for trivial getters/setters/accessors with no logic
- Tests that merely exercise code for coverage without meaningful assertions
- Tests for React component rendering with no logic (pure presentational components)
- Tests for framework-provided behavior (Express routing, Next.js data fetching patterns)
- Tests for pure data structures with no methods
- Tests already covered in the existing test file(s) provided as context
- Tests that only verify a function "doesn't throw" without checking the result
```

**Verification:**

```bash
grep -c '## test-suggestions' prompts/typescript.md prompts/javascript.md
```
Expected: Both show `1`.

**Commit:** `feat: add test-suggestions to typescript.md and javascript.md prompts`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add `## test-suggestions` to `prompts/java.md` and `prompts/kotlin.md`

**Verifies:** test-hammer.AC3.4

**Files:**
- Modify: `prompts/java.md` (append after `## brittle-tests`)
- Modify: `prompts/kotlin.md` (append after `## brittle-tests`)

**Implementation:**

Both Java and Kotlin are JVM languages with similar patterns.

**For java.md:**

```markdown

---

## test-suggestions

You are now a test-suggestion specialist. Given production source code and optionally existing test code, suggest up to **3** high-value tests that are missing.

**Output format:** Same JSON array as other categories. In the `description` field, explain WHAT to test and WHY it matters — not how to implement the test. The `category` field must be `"test-suggestions"`.

**IMPORTANT:** Return at most 3 suggestions. If fewer than 3 are warranted, return fewer. If nothing is worth suggesting, return `[]`.

**WHAT TO SUGGEST** (in priority order):

1. **State transition coverage** — Code with distinct states where transitions between states are not tested. Focus on transitions that change observable behavior.
2. **Error path coverage** — Exception handling paths (try/catch, checked exceptions, custom exceptions) with no corresponding error-case tests. Prioritize paths where the exception transforms data or has side effects.
3. **Business logic boundaries** — Domain-specific boundary conditions where behavior changes (thresholds, limits, mode switches). The boundary must be in THIS code, not in a called function.
4. **Integration seam tests** — Boundaries between components where one side makes assumptions about the other's behavior (interface implementations, callback contracts, event listeners). Focus on assumptions that could silently diverge.
5. **Property-based test opportunities** — Functions with clear invariants: roundtrip encode/decode, idempotency, commutativity. Only suggest when the invariant is non-trivial and not already covered.

**DO NOT SUGGEST:**

- Tests that validate Java language semantics (null reference behavior, autoboxing, type erasure)
- Tests for trivial getters/setters generated by IDE or Lombok
- Tests for `equals`/`hashCode`/`toString` on simple POJOs or records
- Tests for record/enum constructors with no validation logic
- Tests that merely exercise code for coverage without meaningful assertions
- Tests for Spring/Jakarta annotations on simple beans (DI wiring, basic REST endpoints)
- Tests for framework-provided behavior (JPA repository methods, Spring Security defaults)
- Tests for pure data classes or DTOs with no methods
- Tests already covered in the existing test file(s) provided as context
- Tests that only verify a method "doesn't throw" without checking the result
```

**For kotlin.md:** Similar to Java but with Kotlin-specific exclusions:

Replace Java-specific DO NOT SUGGEST items with:
```
- Tests that validate Kotlin language semantics (null safety, smart casts, extension functions)
- Tests for trivial property access with no custom getter/setter logic
- Tests for `data class` generated `equals`/`hashCode`/`toString`/`copy`
- Tests for `sealed class`/`enum class` exhaustiveness (compiler checks this)
- Tests that merely exercise code for coverage without meaningful assertions
- Tests for Ktor/Spring Boot annotations on simple endpoints
- Tests for framework-provided behavior (Exposed/Room DAO methods, coroutine builders)
- Tests for pure data classes with no methods
- Tests already covered in the existing test file(s) provided as context
- Tests that only verify a function "doesn't throw" without checking the result
```

**Verification:**

```bash
grep -c '## test-suggestions' prompts/java.md prompts/kotlin.md
```
Expected: Both show `1`.

**Commit:** `feat: add test-suggestions to java.md and kotlin.md prompts`

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Add `## test-suggestions` to `prompts/swift.md`

**Verifies:** test-hammer.AC3.4

**Files:**
- Modify: `prompts/swift.md` (append after `## brittle-tests`)

**Implementation:**

```markdown

---

## test-suggestions

You are now a test-suggestion specialist. Given production source code and optionally existing test code, suggest up to **3** high-value tests that are missing.

**Output format:** Same JSON array as other categories. In the `description` field, explain WHAT to test and WHY it matters — not how to implement the test. The `category` field must be `"test-suggestions"`.

**IMPORTANT:** Return at most 3 suggestions. If fewer than 3 are warranted, return fewer. If nothing is worth suggesting, return `[]`.

**WHAT TO SUGGEST** (in priority order):

1. **State transition coverage** — Code with distinct states (enums with associated values, state machines) where transitions between states are not tested. Focus on transitions that change observable behavior.
2. **Error path coverage** — Error handling paths (do/try/catch, Result types, throwing functions) with no corresponding error-case tests. Prioritize paths where the error transforms data or has side effects.
3. **Business logic boundaries** — Domain-specific boundary conditions where behavior changes (thresholds, limits, mode switches). The boundary must be in THIS code, not in a called function.
4. **Integration seam tests** — Boundaries between components where one side makes assumptions about the other's behavior (protocol implementations, delegate contracts, notification payloads). Focus on assumptions that could silently diverge.
5. **Property-based test opportunities** — Functions with clear invariants: roundtrip Codable encode/decode, idempotency, commutativity. Only suggest when the invariant is non-trivial and not already covered.

**DO NOT SUGGEST:**

- Tests that validate Swift language semantics (optionals can be nil, value types have copy semantics, protocol conformance)
- Tests for trivial computed properties with no logic
- Tests for `Codable` conformance on simple structs with standard types
- Tests for `Equatable`/`Hashable`/`CustomStringConvertible` on simple types
- Tests that merely exercise code for coverage without meaningful assertions
- Tests for SwiftUI view body rendering with no logic (pure declarative views)
- Tests for framework-provided behavior (URLSession basics, CoreData fetch requests)
- Tests for pure data structures with no methods
- Tests already covered in the existing test file(s) provided as context
- Tests that only verify a function "doesn't throw" without checking the result
```

**Verification:**

```bash
grep -c '## test-suggestions' prompts/swift.md
```
Expected: `1`

**Commit:** `feat: add test-suggestions to swift.md prompt`

<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Add `## test-suggestions` to `prompts/cpp.md` and `prompts/c.md`

**Verifies:** test-hammer.AC3.4

**Files:**
- Modify: `prompts/cpp.md` (append after `## brittle-tests`)
- Modify: `prompts/c.md` (append after `## brittle-tests`)

**Implementation:**

**For cpp.md:**

```markdown

---

## test-suggestions

You are now a test-suggestion specialist. Given production source code and optionally existing test code, suggest up to **3** high-value tests that are missing.

**Output format:** Same JSON array as other categories. In the `description` field, explain WHAT to test and WHY it matters — not how to implement the test. The `category` field must be `"test-suggestions"`.

**IMPORTANT:** Return at most 3 suggestions. If fewer than 3 are warranted, return fewer. If nothing is worth suggesting, return `[]`.

**WHAT TO SUGGEST** (in priority order):

1. **State transition coverage** — Code with distinct states where transitions between states are not tested. Focus on transitions that change observable behavior.
2. **Error path coverage** — Error handling paths (exceptions, error codes, errno, HRESULT) with no corresponding error-case tests. Prioritize paths where the error transforms data or has side effects.
3. **Business logic boundaries** — Domain-specific boundary conditions where behavior changes (thresholds, limits, buffer sizes, mode switches). The boundary must be in THIS code, not in a called function.
4. **Integration seam tests** — Boundaries between components where one side makes assumptions about the other's behavior (virtual function contracts, callback signatures, ABI boundaries). Focus on assumptions that could silently diverge.
5. **Property-based test opportunities** — Functions with clear invariants: roundtrip serialize/deserialize, idempotency, commutativity. Only suggest when the invariant is non-trivial and not already covered.

**DO NOT SUGGEST:**

- Tests that validate C++ language semantics (RAII guarantees, move semantics, template instantiation)
- Tests for trivial constructors/destructors with no logic
- Tests for operator overloads on simple types that delegate to standard operations
- Tests for trivial getters/setters with no logic
- Tests that merely exercise code for coverage without meaningful assertions
- Tests for standard library container usage (std::vector, std::map basic operations)
- Tests for framework-provided behavior (Qt signals/slots wiring, Boost.Asio basic patterns)
- Tests for pure data structures (POD types, simple structs with no methods)
- Tests already covered in the existing test file(s) provided as context
- Tests that only verify a function "doesn't throw" without checking the result
```

**For c.md:**

Similar structure but C-specific:

```markdown

---

## test-suggestions

You are now a test-suggestion specialist. Given production source code and optionally existing test code, suggest up to **3** high-value tests that are missing.

**Output format:** Same JSON array as other categories. In the `description` field, explain WHAT to test and WHY it matters — not how to implement the test. The `category` field must be `"test-suggestions"`.

**IMPORTANT:** Return at most 3 suggestions. If fewer than 3 are warranted, return fewer. If nothing is worth suggesting, return `[]`.

**WHAT TO SUGGEST** (in priority order):

1. **State transition coverage** — Code with distinct states (enum/flag-driven state machines) where transitions between states are not tested. Focus on transitions that change observable behavior.
2. **Error path coverage** — Error handling paths (return codes, errno, goto cleanup) with no corresponding error-case tests. Prioritize paths where the error affects resource cleanup or data integrity.
3. **Business logic boundaries** — Domain-specific boundary conditions where behavior changes (buffer size limits, threshold values, mode switches). The boundary must be in THIS code, not in a called function.
4. **Integration seam tests** — Boundaries between components where one side makes assumptions about the other's behavior (function pointer contracts, callback signatures, struct layout assumptions). Focus on assumptions that could silently diverge.
5. **Property-based test opportunities** — Functions with clear invariants: roundtrip encode/decode, idempotency, commutativity. Only suggest when the invariant is non-trivial and not already covered.

**DO NOT SUGGEST:**

- Tests that validate C language semantics (pointer arithmetic rules, integer promotion, struct padding)
- Tests for trivial struct field access with no logic
- Tests for simple macro definitions with no conditional logic
- Tests that merely exercise code for coverage without meaningful assertions
- Tests for standard library function usage (strlen, memcpy basic patterns)
- Tests for pure data structures (structs with no associated functions)
- Tests already covered in the existing test file(s) provided as context
- Tests that only verify a function "returns 0" without checking side effects
```

**Verification:**

```bash
grep -c '## test-suggestions' prompts/cpp.md prompts/c.md
```
Expected: Both show `1`.

**Commit:** `feat: add test-suggestions to cpp.md and c.md prompts`

<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Add `## test-suggestions` to `prompts/csharp.md`

**Verifies:** test-hammer.AC3.4

**Files:**
- Modify: `prompts/csharp.md` (append after `## brittle-tests`)

**Implementation:**

```markdown

---

## test-suggestions

You are now a test-suggestion specialist. Given production source code and optionally existing test code, suggest up to **3** high-value tests that are missing.

**Output format:** Same JSON array as other categories. In the `description` field, explain WHAT to test and WHY it matters — not how to implement the test. The `category` field must be `"test-suggestions"`.

**IMPORTANT:** Return at most 3 suggestions. If fewer than 3 are warranted, return fewer. If nothing is worth suggesting, return `[]`.

**WHAT TO SUGGEST** (in priority order):

1. **State transition coverage** — Code with distinct states where transitions between states are not tested. Focus on transitions that change observable behavior.
2. **Error path coverage** — Exception handling paths (try/catch, custom exceptions, Task failures) with no corresponding error-case tests. Prioritize paths where the exception transforms data or has side effects.
3. **Business logic boundaries** — Domain-specific boundary conditions where behavior changes (thresholds, limits, mode switches). The boundary must be in THIS code, not in a called function.
4. **Integration seam tests** — Boundaries between components where one side makes assumptions about the other's behavior (interface implementations, event handlers, delegate contracts). Focus on assumptions that could silently diverge.
5. **Property-based test opportunities** — Functions with clear invariants: roundtrip serialize/deserialize, idempotency, commutativity. Only suggest when the invariant is non-trivial and not already covered.

**DO NOT SUGGEST:**

- Tests that validate C# language semantics (nullable reference types, pattern matching exhaustiveness, async/await behavior)
- Tests for trivial auto-properties with no logic
- Tests for record types' generated `Equals`/`GetHashCode`/`ToString`
- Tests for simple POCO/DTO classes with no methods
- Tests that merely exercise code for coverage without meaningful assertions
- Tests for ASP.NET controller action routing or middleware registration
- Tests for Entity Framework basic CRUD operations
- Tests for framework-provided behavior (DI container resolution, configuration binding)
- Tests already covered in the existing test file(s) provided as context
- Tests that only verify a method "doesn't throw" without checking the result
```

**Verification:**

```bash
grep -c '## test-suggestions' prompts/csharp.md
```
Expected: `1`

**Commit:** `feat: add test-suggestions to csharp.md prompt`

<!-- END_TASK_7 -->

<!-- START_TASK_8 -->
### Task 8: Verify all 12 prompt files have `## test-suggestions`

**Verifies:** test-hammer.AC3.4

**Files:** None (verification only)

**Verification:**

```bash
grep -c '## test-suggestions' prompts/rust.md prompts/generic.md prompts/python.md prompts/go.md prompts/typescript.md prompts/javascript.md prompts/java.md prompts/kotlin.md prompts/swift.md prompts/cpp.md prompts/c.md prompts/csharp.md
```

Expected: All 12 files show `1`.

Run the full test suite:
```bash
.venv/bin/pytest tests/ -v
```
Expected: All tests pass.

**Commit:** No commit needed (verification only).

<!-- END_TASK_8 -->
