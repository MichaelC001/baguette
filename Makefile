Baguette:
	./build.sh

test-web:
	node --test 'Tests/Web/**/*.test.js'

# Report docs against docs/documentation-design/ (links, budgets, changelog)
check-docs:
	python3 scripts/check-docs.py

# Release-time changelog scripts: extract → promote → rollover
test-changelog:
	scripts/test-changelog-release.sh

clean:
	swift package clean 2>/dev/null || true
	rm -f Baguette

.PHONY: Baguette clean test-web check-docs test-changelog
