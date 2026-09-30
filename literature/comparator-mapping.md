# Published-method implementation and comparison scope

Source: Tian et al., DOI 10.1109/TNSM.2023.3332509; accepted manuscript in this directory. Equations (12) and (15) define the community score; Algorithm 1 partitions the network, allocates upper-tier resources by community load, solves local VCFR problems and merges their decisions. Equations (1)–(8) specify the utilization/OPEX objective, placement, shared storage, compute, flow, bandwidth and delay constraints. The reported community weights are .6/.4 (printed page 11).

## Implementation

`artifact/security_braess/lbcd.py` retains original graph vertices and load distributions through multilevel community moves. `lbcd_vcfr.py` represents each complete feasible placement/route decision as a column. Binary selection assigns one column to every replica. Deployment binaries charge storage once per node/function; capacity, latency and normalized OPEX terms are supported. Partitioned solves allocate shared budgets proportionally and merge storage by set union. Exhaustive enumeration on a small placement problem checks the objective; separate checks cover storage merging, bandwidth and delay feasibility. Exactness is limited to the supplied column set.

## Matched fixed-placement experiment

The four article substrates contain fixed synthetic VNF resources and two or three eligible chains per tenant. Columns preserve those exact chains, their incidence multiplicities, and each tenant's full demand. The comparison is therefore **LBCD-Heu with fixed placements and enumerated routes**, an explicit adaptation. Every tenant is indivisible for the controlled assignment; Wardrop traffic is divisible. The controlled allocation is evaluated directly, without an equilibrium re-solve.

Use the published load-aware community score with .6/.4 weights on the available substrate, then group requests by their source node's community. The original multi-tier edge/fog/central distinction is absent in these substrates; resources used by multiple groups receive demand-proportional budgets, while group-local resources retain full capacity. This generalization is part of the adaptation and must be disclosed.

Use alpha=1 (maximum compute utilization) to specialize the published tunable objective to load balancing. The substrate has no operating prices or deployment decisions; storage/OPEX terms are inactive in this matched experiment. Retain all link bandwidth bounds. Resource capacities become hard feasibility constraints for the comparator; the article's Wardrop model uses them as delay normalizers. Report maximum utilization and admitted demand to make this difference visible.

Uniform-load variance is treated as a partition-independent zero term. Moves require strictly positive gains. Primary-optimal VCFR ties are resolved lexicographically by tenant and path priority (original left, original right, gateway). Feasible objectives are recomputed after integer rounding; the secondary solve permits an absolute primary-objective tolerance of 1e-7. This rule is explicit because the source leaves ties unspecified. Pinned solver versions and independent resource checks support reproducibility. A global VCFR solve over the same columns isolates the effect of community resource partitioning.

The experiment includes nominal values plus 20 independently seeded demand vectors per topology, each sampled uniformly from [.6,1.4]. Both pre-expansion and expanded decisions are measured. Retain offered/admitted demand, own-baseline penalty, common Wardrop-baseline cost, gateway share, maximum compute/link utilization, exposure scores and runtime. These results support a controlled comparison on the article's eligible chains. They do not reproduce the source paper's unrestricted multi-tier placement experiment.
