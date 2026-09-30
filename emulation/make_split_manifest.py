"""Held-out manifest for the splittable-routing follow-up (braessian-split-protocol.md)."""
import hashlib
import json
from pathlib import Path
import random

here = Path(__file__).resolve().parent
prediction = here / 'results/braessian-prediction/prediction.json'
digest = hashlib.sha256(prediction.read_bytes()).hexdigest()
assert digest.startswith('fd9d68f0'), 'frozen prediction changed'
frozen = json.loads(prediction.read_text())
caps = sorted({0, .25, frozen['screened_cap'], 1})
runs = [{'rate': frozen['rate'], 'seed': seed, 'cap': cap, 'seconds': 90, 'activate': 20, 'step_at': 60,
         'step_factor': 1.15, 'phasing': mode, 'shared_service_ms': 2.0, 'replica_service_ms': 0.2,
         'replica_delay_ms': 5, 'split_step': 0.2}
        for seed in range(7201, 7206) for mode in ['staggered', 'synchronized'] for cap in caps]
random.Random(7199).shuffle(runs)
manifest = {'purpose': 'Splittable-routing follow-up; protocol in braessian-split-protocol.md',
            'prediction_sha256': digest, 'order_seed': 7199, 'caps': caps,
            'windows': {'before': [10, 20], 'expanded': [45, 60], 'step': [75, 90]},
            'settle_search': [40, 30], 'runs': runs}
(here / 'braessian-split-manifest.json').write_text(json.dumps(manifest, indent=2))
print(len(runs), 'runs; caps', caps)
