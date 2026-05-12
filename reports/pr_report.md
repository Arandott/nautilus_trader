Count CLEAR toward limit; add tests for limits and flags

# Pull Request

## Summary

Updated Tardis CSV delta streaming to always emit a synthetic CLEAR at snapshot boundaries (including batched/Python paths) and to count CLEAR events toward the `limit`. Adjusted chunking/flagging so `F_LAST` is only set when the stream truly ends (limit reached or EOF), not merely at chunk boundaries, and added a pending-record path to avoid losing deltas when CLEAR fills a chunk.

## Related Issues/PRs

None.

## Type of change

- [x] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] Improvement (non-breaking)
- [ ] Breaking change (impacts existing behavior)
- [ ] Documentation update
- [ ] Maintenance / chore

## Breaking change details (if applicable)

Not applicable.

## Documentation

- [ ] Documentation changes follow the style guide (`docs/developer_guide/docs.md`)

## Release notes

- [ ] I added a concise entry to `RELEASES.md` that follows the existing conventions (when applicable)

## Testing

**Ensure new or changed logic is covered by tests.**

- [ ] Affected code paths are already covered by the test suite
- [x] I added/updated tests to cover new or changed logic

Added/updated stream tests in `crates/adapters/tardis/src/csv/stream.rs` to cover CLEAR insertion on snapshot boundaries, limit counting (including CLEAR), and `F_LAST` flag behavior for both chunked and limited streaming. Tests were not run in this session.
