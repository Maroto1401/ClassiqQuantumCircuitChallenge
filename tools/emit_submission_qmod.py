import os as _os, pathlib as _pl
ROOT = _pl.Path(__file__).resolve().parents[1]
_os.chdir(ROOT)          # all paths below are repo-relative
import sys, pathlib
sys.path.insert(0, str(ROOT))
from classiq import create_model, write_qmod, Constraints, OptimizationParameter
from submission_model import main

ROOT = pathlib.Path(".")
constraints = Constraints(optimization_parameter=OptimizationParameter.DEPTH, max_width=18)
model = create_model(main, constraints=constraints)
write_qmod(model, "submission", directory=ROOT, decimal_precision=17)
print("wrote submission.qmod (+ submission.synthesis_options.json)")
