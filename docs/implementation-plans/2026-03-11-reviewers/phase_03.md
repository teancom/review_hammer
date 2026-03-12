# Review Hammer Implementation Plan — Phase 3: Language Prompt Templates

**Goal:** All 12 language-specific prompt files with tuned specialist categories, plus extension-to-language mapping in the script

**Architecture:** Each language gets its own markdown prompt file in `prompts/`. The preamble and H2 section structure matches `generic.md` but with language-specific context, specialist naming (e.g., "memory-safety" instead of "null-safety" for C/Rust), and tailored DO NOT REPORT constraints. The script maps file extensions to language keys used to select prompt files.

**Tech Stack:** Markdown (prompt templates), Python (extension mapping)

**Scope:** 6 phases from original design (this is phase 3 of 6)

**Codebase verified:** 2026-03-11 — `prompts/generic.md` created in Phase 2. `review_file.py` exists from Phase 2 with prompt template loading logic.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### reviewers.AC3: Language-aware prompts
- **reviewers.AC3.1 Success:** Each of 12 language prompt files contains language-specific specialist sections with appropriate DO NOT REPORT constraints
- **reviewers.AC3.2 Success:** File extension correctly maps to language (e.g., .kt->kotlin, .swift->swift, .rs->rust)
- **reviewers.AC3.3 Edge:** Unknown file extension falls back to generic.md

---

<!-- START_TASK_1 -->
### Task 1: Add extension-to-language mapping in review_file.py

**Verifies:** reviewers.AC3.2, reviewers.AC3.3

**Files:**
- Modify: `scripts/review_file.py`

**Implementation:**

Add a module-level constant `EXTENSION_MAP` and a function `detect_language(file_path: str) -> str`:

```python
EXTENSION_MAP = {
    ".py": "python",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".java": "java",
    ".cs": "csharp",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".rs": "rust",
    ".go": "go",
    ".swift": "swift",
}
```

The `detect_language` function extracts the file extension and looks it up in `EXTENSION_MAP`. If not found, returns `"generic"`.

Also make the `--language` CLI argument optional — if not provided, auto-detect from file extension. If provided, it overrides auto-detection.

**Testing:**

Tests must verify:
- reviewers.AC3.2: Each extension in the map resolves to the correct language key (`.kt` -> `"kotlin"`, `.swift` -> `"swift"`, `.rs` -> `"rust"`, `.py` -> `"python"`, etc.)
- reviewers.AC3.3: Unknown extensions (`.xyz`, `.rb`, `.lua`) return `"generic"`
- Multi-extension support (`.cpp`, `.cc`, `.cxx` all map to `"cpp"`)

Test file: `tests/test_review_file.py` (add to existing test file from Phase 2)

**Verification:**
Run: `.venv/bin/python3 -m pytest tests/test_review_file.py -v`
Expected: All tests pass

**Commit:** `feat: add file extension to language detection`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create Python prompt template

**Verifies:** reviewers.AC3.1

**Files:**
- Create: `prompts/python.md`

**Implementation:**

**This is the reference implementation.** Use this template's structure and level of detail as the pattern for all other language templates in Tasks 3-6. Follow the same structure as `generic.md` but with Python-specific context. Key differences from generic:

**Preamble:** Mentions Python-specific context (GIL, asyncio, generators, context managers, type hints).

**Production specialists — language-specific tuning:**

- **`## race-conditions`**: Focus on asyncio race conditions, shared mutable state across coroutines, GIL-related misconceptions (GIL protects reference counts but not application logic). DO NOT REPORT: Single-threaded scripts, asyncio code that uses proper locks/events, GIL-protected operations on simple types.

- **`## null-safety`**: Focus on `None` dereferences, `Optional` types used without checks, `dict.get()` results used without None checks, attribute access on potentially-None values. DO NOT REPORT: Values with type hints showing non-Optional, values checked by `if x is not None` guard, default parameter values.

- **`## resource-leaks`**: Focus on file handles opened without `with` statement, unclosed sockets/connections, database connections not returned to pool, `open()` without corresponding `close()` or context manager. DO NOT REPORT: Resources used with `with` statement (context managers), `tempfile` module resources (auto-cleaned), subprocess with `communicate()`.

- **`## logic-errors`**: Add Python-specific: mutable default arguments (`def f(x=[])`), `is` vs `==` for value comparison, integer comparison beyond cached range, `except Exception` catching `StopIteration` in generators. DO NOT REPORT: `is None` / `is not None` checks (correct usage of `is`), intentional mutable defaults with documentation.

- **`## error-handling`**: Focus on bare `except:` catching everything including `SystemExit`/`KeyboardInterrupt`, `except Exception` that should be more specific, errors logged but not re-raised when callers need them. DO NOT REPORT: `except Exception` at top-level entry points, intentional suppression with `contextlib.suppress()`.

- **`## state-management`**: Focus on class attributes shared across instances (mutable class-level defaults), module-level state mutation, `__dict__` manipulation, descriptor protocol misuse. DO NOT REPORT: Properly documented singleton patterns, module-level constants (immutable).

**Test specialists** — same as generic but add Python-specific DO NOT REPORT:

- **`## testing-nothing`**: Also DO NOT REPORT: pytest fixtures that provide setup (not assertions themselves), parameterized test markers.
- **`## missing-assertions`**: Also DO NOT REPORT: `pytest.raises` context manager as assertion.
- **`## over-mocking`**: Also DO NOT REPORT: `unittest.mock.patch` for environment variables, `monkeypatch` for env/path.
- **`## brittle-tests`**: Also DO NOT REPORT: `assert repr(x)` tests for debugging output.
- **`## missing-edge-cases`**: Also DO NOT REPORT: Type-checked code where mypy prevents the edge case.

**Verification:**
Run: `grep '^## ' prompts/python.md | wc -l`
Expected: 11 (6 production + 5 test sections)

**Commit:** `feat: add Python prompt template`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Create C and C++ prompt templates

**Verifies:** reviewers.AC3.1

**Files:**
- Create: `prompts/c.md`
- Create: `prompts/cpp.md`

**Implementation:**

**C template (`prompts/c.md`):**
- Preamble: C-specific context (manual memory management, pointer arithmetic, undefined behavior, preprocessor macros)
- `## race-conditions`: pthread races, shared globals without mutex, signal handler data races. DO NOT REPORT: Single-threaded programs, properly mutex-protected access.
- `## memory-safety` (renamed from null-safety): NULL pointer dereference, buffer overflows, use-after-free, double-free, stack buffer overflow, uninitialized memory reads. DO NOT REPORT: Pointers checked against NULL before use, `sizeof`-bounded operations.
- `## resource-leaks`: malloc without free, fopen without fclose, unclosed file descriptors, leaked semaphores. DO NOT REPORT: Resources freed in a paired function (init/cleanup pattern), OS-level cleanup on exit for short-lived programs.
- `## logic-errors`: Add C-specific: signed/unsigned comparison, integer truncation, sizeof on pointer vs array, macro expansion side effects. DO NOT REPORT: Compiler warnings already catching the issue.
- `## error-handling`: Unchecked return values from system calls (malloc, fopen, read, write), errno not checked after failures. DO NOT REPORT: Void-returning functions, assert() for programmer errors.
- `## state-management`: Global state mutation, static local variables across calls, struct partial initialization. DO NOT REPORT: Const globals, static constants.
- Test specialists: Same as generic with no C-specific additions (C test frameworks vary widely).

**C++ template (`prompts/cpp.md`):**
- Preamble: C++ context (RAII, smart pointers, move semantics, templates, exception safety)
- `## race-conditions`: Same as C plus `std::thread` races, lock ordering issues, `shared_ptr` ref count races. DO NOT REPORT: `std::atomic` operations, `std::lock_guard`/`std::unique_lock` protected sections.
- `## memory-safety`: Raw pointer dereference, dangling references from moved-from objects, iterator invalidation, use-after-move. DO NOT REPORT: `unique_ptr`/`shared_ptr` managed memory, references bound to valid stack objects, RAII-managed resources.
- `## resource-leaks`: Raw `new` without `delete`, resources not in RAII wrappers. DO NOT REPORT: Smart pointer managed resources, RAII wrappers (fstream, lock_guard).
- Other production categories: Tuned similarly with C++-specific patterns.
- Test specialists: Google Test / Catch2 patterns in DO NOT REPORT.

**Verification:**
Run: `for f in prompts/c.md prompts/cpp.md; do echo "$f:"; grep '^## ' "$f" | wc -l; done`
Expected: Both show 11

**Commit:** `feat: add C and C++ prompt templates`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Create Java and C# prompt templates

**Verifies:** reviewers.AC3.1

**Files:**
- Create: `prompts/java.md`
- Create: `prompts/csharp.md`

**Implementation:**

**Java template (`prompts/java.md`):**
- Preamble: Java context (JVM, garbage collection, checked exceptions, generics with type erasure, synchronized blocks)
- `## race-conditions`: Unsynchronized shared mutable state, non-atomic compound operations, `HashMap` concurrent access, double-checked locking without volatile. DO NOT REPORT: `synchronized` blocks, `ConcurrentHashMap`, `volatile` fields, `AtomicReference` operations.
- `## null-safety`: NullPointerException risks from unguarded method calls on nullable returns, Optional.get() without isPresent(), stream operations on potentially-null collections. DO NOT REPORT: `@NonNull` annotated parameters, Optional.map/orElse chains, Objects.requireNonNull guards.
- `## resource-leaks`: JDBC connections, InputStreams, database ResultSets not in try-with-resources. DO NOT REPORT: try-with-resources (AutoCloseable), Spring-managed beans, connection pools.
- `## logic-errors`: `==` on objects instead of `.equals()`, String comparison with `==`, iterator concurrent modification, `hashCode`/`equals` contract violations. DO NOT REPORT: `==` on primitives, enum comparison with `==`.
- `## error-handling`: Caught checked exceptions silently swallowed, overly broad `catch (Exception e)`, exceptions caught and wrapped losing the cause chain. DO NOT REPORT: Exception logging with re-throw, `@SneakyThrows` (Lombok), Spring `@ExceptionHandler`.
- `## state-management`: Mutable fields without synchronization, `static` mutable fields, JavaBean partial setter updates. DO NOT REPORT: Immutable records, final fields, effectively-final locals.
- Test specialists tuned for JUnit 5 / Mockito patterns.

**C# template (`prompts/csharp.md`):**
- Similar to Java but with C#-specific: async/await patterns, `IDisposable`/`using` blocks, LINQ, nullable reference types (C# 8+), `record` types.
- `## null-safety`: Nullable reference types, `!` null-forgiving operator misuse, null propagation (`?.`) silently returning null. DO NOT REPORT: `#nullable enable` annotated code, `??` null-coalescing with defaults.
- `## resource-leaks`: `IDisposable` without `using`, `HttpClient` misuse (should be singleton). DO NOT REPORT: `using` statements/declarations, DI container-managed lifetimes.

**Verification:**
Run: `for f in prompts/java.md prompts/csharp.md; do echo "$f:"; grep '^## ' "$f" | wc -l; done`
Expected: Both show 11

**Commit:** `feat: add Java and C# prompt templates`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Create JavaScript and TypeScript prompt templates

**Verifies:** reviewers.AC3.1

**Files:**
- Create: `prompts/javascript.md`
- Create: `prompts/typescript.md`

**Implementation:**

**JavaScript template (`prompts/javascript.md`):**
- Preamble: JS context (single-threaded event loop, prototypal inheritance, closures, hoisting, implicit coercion)
- `## race-conditions`: Async race conditions (Promise.all without error isolation, unguarded shared state across async callbacks, event handler ordering). DO NOT REPORT: Sequential await chains, properly guarded state with locks/semaphores, single event loop guarantees for synchronous code.
- `## null-safety` (named `type-safety` for JS): `undefined` access, missing property checks, `null` vs `undefined` confusion, `typeof` guard gaps. DO NOT REPORT: Optional chaining (`?.`) with nullish coalescing (`??`), default parameters, destructuring defaults.
- `## resource-leaks`: Event listeners not removed, setInterval without clearInterval, unfinished Promises, unclosed streams. DO NOT REPORT: Framework-managed lifecycle (React useEffect cleanup), short-lived scripts.
- `## logic-errors`: `==` vs `===`, `typeof null === 'object'`, falsy value confusion (0, '', NaN, null, undefined), array `.sort()` without comparator on numbers. DO NOT REPORT: Intentional loose equality with documentation.
- Other categories tuned similarly for JS patterns.
- Test specialists tuned for Jest / Vitest / Mocha patterns.

**TypeScript template (`prompts/typescript.md`):**
- Preamble: TS context (structural typing, type narrowing, generics, declaration merging, `any` escape hatch)
- `## null-safety` (named `type-safety`): Non-null assertion (`!`) misuse, `as` type casting bypassing checks, `any` propagation hiding type errors, missing discriminated union exhaustiveness. DO NOT REPORT: Proper type guards, `satisfies` operator usage, narrowing through control flow.
- Other categories similar to JS but with TS-specific DO NOT REPORT for patterns the type system already catches.
- Test specialists tuned for Jest / Vitest with TypeScript-specific patterns (type assertion in tests, `@ts-expect-error` in test files).

**Verification:**
Run: `for f in prompts/javascript.md prompts/typescript.md; do echo "$f:"; grep '^## ' "$f" | wc -l; done`
Expected: Both show 11

**Commit:** `feat: add JavaScript and TypeScript prompt templates`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Create Kotlin, Rust, Go, and Swift prompt templates

**Verifies:** reviewers.AC3.1

**Files:**
- Create: `prompts/kotlin.md`
- Create: `prompts/rust.md`
- Create: `prompts/go.md`
- Create: `prompts/swift.md`

**Implementation:**

**Kotlin template (`prompts/kotlin.md`):**
- Preamble: Kotlin context (null safety built-in, coroutines, data classes, sealed classes, extension functions)
- `## race-conditions`: Coroutine race conditions (shared mutable state across coroutines without Mutex, unsafe `GlobalScope.launch`, channel misuse, StateFlow/SharedFlow races). DO NOT REPORT: `Mutex`-protected sections, `withContext(Dispatchers.Main)` for UI updates, `atomic` operations.
- `## null-safety`: `!!` non-null assertion operator misuse, platform types from Java interop, unsafe casts with `as` instead of `as?`. DO NOT REPORT: Safe calls (`?.`), elvis operator (`?:`), `let`/`also` null checks, smart casts after null check.
- Other categories tuned for Kotlin/JVM patterns.
- Test specialists tuned for JUnit 5 / MockK / Kotest patterns.

**Rust template (`prompts/rust.md`):**
- Preamble: Rust context (ownership, borrowing, lifetimes, traits, unsafe blocks, no GC)
- `## memory-safety` (renamed): `unsafe` block misuse, raw pointer dereference without validation, lifetime annotation errors, transmute misuse. DO NOT REPORT: Safe Rust code (compiler guarantees), `unsafe` blocks with documented safety invariants, `Pin`/`Unpin` usage.
- `## race-conditions`: Data races in `unsafe` code, `Arc` without `Mutex`, `Send`/`Sync` trait bound violations. DO NOT REPORT: Rust's type system prevents data races in safe code, `Arc<Mutex<T>>` patterns, channel-based concurrency.
- Other categories tuned for Rust patterns (e.g., `resource-leaks`: `ManuallyDrop` without dropping, `forget` misuse; but DO NOT REPORT RAII/Drop-managed resources).

**Go template (`prompts/go.md`):**
- Preamble: Go context (goroutines, channels, interfaces, error values, defer, no exceptions)
- `## race-conditions`: Goroutine data races, unbuffered channel deadlocks, `sync.WaitGroup` misuse, map concurrent access. DO NOT REPORT: `sync.Mutex`-protected access, channel-based communication, `sync.Map`, `-race` detector-clean code.
- `## null-safety` (named `nil-safety`): Nil pointer dereference on interfaces, nil map writes, nil function calls, nil slice operations that panic. DO NOT REPORT: Nil slice append (valid in Go), nil map reads (return zero value), checked nil guards.
- `## error-handling`: Ignored error returns (`_ = doSomething()`), error checked but wrong error returned, deferred close errors ignored. DO NOT REPORT: Intentional `_ =` with comment, top-level `log.Fatal` on startup errors.
- Other categories tuned for Go idioms.

**Swift template (`prompts/swift.md`):**
- Preamble: Swift context (ARC, optionals, protocols, actors, async/await, value types vs reference types)
- `## null-safety`: Force unwrap (`!`) on optionals, `as!` forced cast, implicitly unwrapped optionals (`!`) in properties. DO NOT REPORT: `guard let`/`if let` unwrapping, `??` nil-coalescing, optional chaining.
- `## race-conditions`: `@MainActor` violations, shared mutable state without actor isolation, `DispatchQueue` race conditions. DO NOT REPORT: Actor-isolated state, `@Sendable` closures, structured concurrency with `TaskGroup`.
- `## resource-leaks`: Retain cycles (strong reference cycles in closures, delegate patterns without `weak`/`unowned`). DO NOT REPORT: `[weak self]` capture lists, value types (no retain cycles), `@objc` protocol delegates with `weak`.
- Other categories tuned for Swift/Apple patterns.

**Verification:**
Run: `for f in prompts/kotlin.md prompts/rust.md prompts/go.md prompts/swift.md; do echo "$f:"; grep '^## ' "$f" | wc -l; done`
Expected: All show 11

**Commit:** `feat: add Kotlin, Rust, Go, and Swift prompt templates`
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Verify all prompt templates and extension mapping

**Verifies:** reviewers.AC3.1, reviewers.AC3.2, reviewers.AC3.3

**Step 1: Verify all 12 prompt files exist with correct section count**

Run:
```bash
for f in prompts/generic.md prompts/python.md prompts/c.md prompts/cpp.md prompts/java.md prompts/csharp.md prompts/javascript.md prompts/typescript.md prompts/kotlin.md prompts/rust.md prompts/go.md prompts/swift.md; do
  count=$(grep -c '^## ' "$f" 2>/dev/null || echo "MISSING")
  echo "$f: $count sections"
done
```
Expected: All 12 files show "11 sections"

**Step 2: Verify extension mapping covers all required extensions**

Run:
```bash
.venv/bin/python3 -c "
import sys; sys.path.insert(0, 'scripts')
from review_file import detect_language
tests = {
    'foo.py': 'python', 'foo.c': 'c', 'foo.h': 'c',
    'foo.cpp': 'cpp', 'foo.cc': 'cpp', 'foo.java': 'java',
    'foo.cs': 'csharp', 'foo.js': 'javascript', 'foo.jsx': 'javascript',
    'foo.ts': 'typescript', 'foo.tsx': 'typescript',
    'foo.kt': 'kotlin', 'foo.rs': 'rust', 'foo.go': 'go',
    'foo.swift': 'swift', 'foo.rb': 'generic', 'foo.xyz': 'generic',
}
for path, expected in tests.items():
    result = detect_language(path)
    status = '✓' if result == expected else '✗'
    print(f'{status} {path} -> {result} (expected {expected})')
"
```
Expected: All lines show ✓

**Step 3: Run full test suite**

Run: `.venv/bin/python3 -m pytest tests/ -v`
Expected: All tests pass

No commit for this task — it's a verification step only.
<!-- END_TASK_7 -->
