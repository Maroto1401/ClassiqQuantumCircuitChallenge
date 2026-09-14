.PHONY: install test diag demo score board clean
install:
	pip install -e ".[dev]"
test:
	pytest -q
diag:
	qo diag
demo:
	qo run --cover minterm --lowering serial_mcz
	qo run --cover pprm    --lowering serial_mcz
	qo leaderboard
score:
	qo score --basis $(BASIS)
board:
	qo leaderboard --basis $(BASIS)
clean:
	rm -rf data/artifacts/ir data/artifacts/circuit data/artifacts/diag
