# NetworkX Algorithm Reference

Full function list organized by category. All functions are in the `nx` namespace unless noted.
Version: NetworkX 3.6.x — https://networkx.org/documentation/stable/reference/algorithms/

---

## Table of Contents

1. [Shortest Paths](#shortest-paths)
2. [Centrality](#centrality)
3. [Community Detection](#community-detection)
4. [Connectivity](#connectivity)
5. [Spanning Trees and Branchings](#spanning-trees-and-branchings)
6. [Flows and Cuts](#flows-and-cuts)
7. [Traversal](#traversal)
8. [Cycles and DAGs](#cycles-and-dags)
9. [Cliques](#cliques)
10. [Matching](#matching)
11. [Clustering and Triangles](#clustering-and-triangles)
12. [Graph Operators](#graph-operators)
13. [Distance Measures](#distance-measures)
14. [Link Analysis (PageRank, HITS)](#link-analysis)
15. [Link Prediction](#link-prediction)
16. [Components](#components)
17. [Bipartite Algorithms](#bipartite-algorithms)
18. [Coloring](#coloring)
19. [Isomorphism](#isomorphism)
20. [Cores and Degeneracy](#cores-and-degeneracy)
21. [Planarity](#planarity)
22. [Small World Measures](#small-world-measures)
23. [Other Algorithms](#other-algorithms)

---

## Shortest Paths

### Unweighted

| Function | Description |
|---|---|
| `shortest_path(G, source, target)` | One shortest path (auto-selects algorithm) |
| `shortest_path_length(G, source, target)` | Length of shortest path |
| `all_shortest_paths(G, source, target)` | All shortest paths between two nodes |
| `has_path(G, source, target)` | Boolean: path exists? |
| `average_shortest_path_length(G)` | Mean over all pairs |
| `single_source_shortest_path(G, source)` | Dict of paths from source |
| `single_source_shortest_path_length(G, source)` | Dict of lengths from source |
| `single_target_shortest_path(G, target)` | Dict of paths to target |
| `all_pairs_shortest_path(G)` | Generator of (source, dict) |
| `all_pairs_shortest_path_length(G)` | Generator of (source, dict) |
| `bidirectional_shortest_path(G, source, target)` | Bidirectional BFS |
| `predecessor(G, source)` | Predecessor dict for BFS tree |

### Dijkstra (non-negative weights)

| Function | Description |
|---|---|
| `dijkstra_path(G, source, target, weight)` | Shortest path |
| `dijkstra_path_length(G, source, target, weight)` | Path length |
| `single_source_dijkstra(G, source)` | (lengths, paths) from source |
| `single_source_dijkstra_path(G, source)` | Paths from source |
| `single_source_dijkstra_path_length(G, source)` | Lengths from source |
| `multi_source_dijkstra(G, sources)` | From multiple sources |
| `all_pairs_dijkstra(G)` | All-pairs generator |
| `all_pairs_dijkstra_path(G)` | All-pairs paths |
| `all_pairs_dijkstra_path_length(G)` | All-pairs lengths |
| `bidirectional_dijkstra(G, source, target)` | Faster for single-pair |

### Bellman-Ford (negative weights, no negative cycles)

| Function | Description |
|---|---|
| `bellman_ford_path(G, source, target, weight)` | Shortest path |
| `bellman_ford_path_length(G, source, target)` | Path length |
| `single_source_bellman_ford(G, source)` | (lengths, paths) |
| `all_pairs_bellman_ford_path(G)` | All-pairs paths |
| `all_pairs_bellman_ford_path_length(G)` | All-pairs lengths |
| `negative_edge_cycle(G, weight)` | True if negative cycle exists |
| `find_negative_cycle(G, source, weight)` | Return the negative cycle |

### Floyd-Warshall (all-pairs, dense graphs)

| Function | Description |
|---|---|
| `floyd_warshall(G, weight)` | Dict-of-dicts of distances |
| `floyd_warshall_numpy(G, weight)` | NumPy matrix |
| `floyd_warshall_predecessor_and_distance(G)` | (pred, dist) dicts |
| `reconstruct_path(source, target, predecessors)` | Recover path from pred dict |
| `johnson(G, weight)` | All-pairs via Johnson's reweighting |

### A* Search

| Function | Description |
|---|---|
| `astar_path(G, source, target, heuristic, weight)` | A* shortest path |
| `astar_path_length(G, source, target, heuristic, weight)` | A* path length |

---

## Centrality

All return `{node: float}`.

### Degree

| Function | Description |
|---|---|
| `degree_centrality(G)` | Normalized degree |
| `in_degree_centrality(G)` | Normalized in-degree (DiGraph) |
| `out_degree_centrality(G)` | Normalized out-degree (DiGraph) |

### Eigenvector and Katz

| Function | Description |
|---|---|
| `eigenvector_centrality(G, max_iter, tol, weight)` | Power iteration |
| `eigenvector_centrality_numpy(G, weight)` | NumPy eigenvector solver |
| `katz_centrality(G, alpha, beta, weight)` | Katz centrality |
| `katz_centrality_numpy(G, alpha, beta)` | NumPy Katz solver |

### Closeness

| Function | Description |
|---|---|
| `closeness_centrality(G, u, distance)` | Inverse mean distance |
| `incremental_closeness_centrality(G, edge)` | Update after edge addition/removal |
| `current_flow_closeness_centrality(G)` | Resistance-based closeness |
| `information_centrality(G)` | Alias for current-flow closeness |

### Betweenness

| Function | Description |
|---|---|
| `betweenness_centrality(G, k, normalized, weight)` | Fraction of paths through node |
| `betweenness_centrality_subset(G, sources, targets)` | Subset version |
| `edge_betweenness_centrality(G, normalized, weight)` | Betweenness on edges |
| `edge_betweenness_centrality_subset(G, sources, targets)` | Subset edge version |
| `current_flow_betweenness_centrality(G)` | Resistance-based betweenness |
| `edge_current_flow_betweenness_centrality(G)` | Resistance-based edge betweenness |
| `approximate_current_flow_betweenness_centrality(G)` | Approximation |
| `communicability_betweenness_centrality(G)` | Walk-based betweenness |

### Group Centrality

| Function | Description |
|---|---|
| `group_betweenness_centrality(G, C)` | Betweenness of a node group |
| `group_closeness_centrality(G, S)` | Closeness of a node group |
| `group_degree_centrality(G, S)` | Degree of a node group |
| `group_in_degree_centrality(G, S)` | In-degree group centrality |
| `group_out_degree_centrality(G, S)` | Out-degree group centrality |
| `prominent_group(G, k, weight)` | Find best group of size k |

### Other Centrality Measures

| Function | Description |
|---|---|
| `harmonic_centrality(G)` | Handles disconnected graphs |
| `load_centrality(G)` | Fraction of paths (unweighted) |
| `subgraph_centrality(G)` | Walk-based, involves matrix exponential |
| `subgraph_centrality_exp(G)` | Same using expm |
| `estrada_index(G)` | Sum of subgraph centralities |
| `dispersion(G, u, v)` | How dispersed are shared neighbors |
| `local_reaching_centrality(G, v)` | Fraction of nodes reachable from v |
| `global_reaching_centrality(G)` | Mean of local reaching centralities |
| `percolation_centrality(G)` | Weighted betweenness (percolation) |
| `second_order_centrality(G)` | Standard deviation of return times |
| `trophic_levels(G)` | Food-web trophic level |
| `voterank(G, number_of_nodes)` | Influence ranking via voting |
| `laplacian_centrality(G)` | Energy-based centrality |

---

## Community Detection

Access via `from networkx.algorithms import community` or `nx.community.*`.

| Function | Description |
|---|---|
| `community.louvain_communities(G, weight, seed)` | Best all-around; maximizes modularity |
| `community.greedy_modularity_communities(G, weight)` | Clauset-Newman-Moore |
| `community.naive_greedy_modularity_communities(G)` | Simpler but slower |
| `community.girvan_newman(G, most_valuable_edge)` | Divisive; yields each level |
| `community.label_propagation_communities(G)` | Fast, stochastic |
| `community.asyn_lpa_communities(G, weight, seed)` | Async label propagation |
| `community.fast_label_propagation_communities(G)` | Faster variant |
| `community.k_clique_communities(G, k)` | Overlapping clique percolation |
| `community.asyn_fluidc(G, k, seed)` | Fluid communities, k fixed |
| `community.kernighan_lin_bisection(G)` | Bipartition only |
| `community.lukes_partitioning(G, max_size)` | Tree partitioning |
| `community.greedy_source_expansion(G, source)` | Local community of a node |
| `community.modularity(G, communities, weight)` | Measure partition quality |
| `community.partition_quality(G, partition)` | (coverage, performance) tuple |
| `community.is_partition(G, communities)` | Validate partition |

---

## Connectivity

| Function | Description |
|---|---|
| `is_connected(G)` | All nodes in one component? |
| `number_connected_components(G)` | Count of components |
| `connected_components(G)` | Generator of sets |
| `node_connected_component(G, n)` | Component containing node n |
| `is_strongly_connected(DG)` | DiGraph: path between all pairs? |
| `is_weakly_connected(DG)` | DiGraph: connected if edges undirected? |
| `strongly_connected_components(DG)` | Generator of SCCs |
| `weakly_connected_components(DG)` | Generator |
| `condensation(DG)` | DAG of SCCs |
| `node_connectivity(G, s, t)` | Min nodes to disconnect s from t |
| `edge_connectivity(G, s, t)` | Min edges to disconnect s from t |
| `all_node_cuts(G)` | Generator of minimum node cuts |
| `minimum_node_cut(G, s, t)` | Min node cut set |
| `minimum_edge_cut(G, s, t)` | Min edge cut set |
| `stoer_wagner(G)` | Global min cut (Stoer-Wagner) |
| `is_biconnected(G)` | No articulation points? |
| `biconnected_components(G)` | Generator of biconnected components |
| `articulation_points(G)` | Nodes whose removal disconnects |
| `bridges(G)` | Edges whose removal disconnects |

---

## Spanning Trees and Branchings

| Function | Description |
|---|---|
| `minimum_spanning_tree(G, weight, algorithm)` | MST (algorithms: kruskal, prim, boruvka) |
| `maximum_spanning_tree(G, weight, algorithm)` | Maximum spanning tree |
| `minimum_spanning_edges(G, weight, data)` | Iterator over MST edges |
| `maximum_spanning_edges(G, weight, data)` | Iterator |
| `random_spanning_tree(G, weight, seed)` | Uniformly random spanning tree |
| `minimum_spanning_arborescence(DG, attr)` | Directed MST (Edmonds') |
| `maximum_spanning_arborescence(DG, attr)` | Directed maximum |
| `is_arborescence(DG)` | DiGraph: valid arborescence? |
| `is_branching(DG)` | DiGraph: valid branching? |

---

## Flows and Cuts

| Function | Description |
|---|---|
| `maximum_flow(G, s, t, capacity)` | (value, dict) — Preflow-push by default |
| `maximum_flow_value(G, s, t, capacity)` | Value only |
| `minimum_cut(G, s, t, capacity)` | (value, partition) |
| `minimum_cut_value(G, s, t, capacity)` | Cut value only |
| `max_flow_min_cut(G, s, t)` | Both together |
| `min_cost_flow(G)` | Min-cost flow (needs demand/capacity/weight) |
| `min_cost_flow_cost(G)` | Cost of min-cost flow |
| `capacity_scaling(G)` | Capacity-scaling min-cost flow |
| `network_simplex(G)` | Network simplex min-cost flow |
| `gomory_hu_tree(G, capacity)` | All-pairs max-flow via Gomory-Hu tree |

**Flow algorithms** (pass as `flow_func` parameter):
- `algorithms.flow.edmonds_karp`
- `algorithms.flow.shortest_augmenting_path`
- `algorithms.flow.preflow_push`
- `algorithms.flow.dinitz`
- `algorithms.flow.boykov_kolmogorov`

---

## Traversal

| Function | Description |
|---|---|
| `bfs_edges(G, source, depth_limit)` | BFS edge generator |
| `bfs_tree(G, source)` | BFS spanning tree (DiGraph) |
| `bfs_predecessors(G, source)` | Iterator of (node, predecessor) |
| `bfs_successors(G, source)` | Iterator of (node, successors) |
| `bfs_layers(G, sources)` | Generator of BFS levels |
| `bfs_labeled_edges(G, source)` | (u, v, label) where label=tree/forward/cross |
| `dfs_edges(G, source, depth_limit)` | DFS edge generator |
| `dfs_tree(G, source)` | DFS spanning tree |
| `dfs_predecessors(G, source)` | Predecessor dict |
| `dfs_successors(G, source)` | Successor dict |
| `dfs_preorder_nodes(G, source)` | Preorder node generator |
| `dfs_postorder_nodes(G, source)` | Postorder node generator |
| `dfs_labeled_edges(G, source)` | (u, v, label) — tree/forward/back/cross |
| `edge_dfs(G, source)` | Edge DFS (visits each edge) |
| `edge_bfs(G, source)` | Edge BFS |

---

## Cycles and DAGs

| Function | Description |
|---|---|
| `find_cycle(G, source, orientation)` | One cycle (raises if none) |
| `simple_cycles(DG)` | All directed simple cycles |
| `all_simple_cycles(G)` | All undirected simple cycles |
| `cycle_basis(G, root)` | Minimum cycle basis |
| `minimum_cycle_basis(G, weight)` | Weighted minimum cycle basis |
| `chordless_cycles(G, length_bound)` | Cycles with no chord |
| `girth(G)` | Length of shortest cycle |
| `is_directed_acyclic_graph(DG)` | Is it a DAG? |
| `topological_sort(DG)` | Linear ordering (raises if cycle) |
| `all_topological_sorts(DG)` | Generator of all valid orderings |
| `lexicographic_topological_sort(DG)` | Deterministic topological order |
| `topological_generations(DG)` | Groups of nodes by topological level |
| `ancestors(DG, source)` | All nodes that can reach source |
| `descendants(DG, source)` | All nodes reachable from source |
| `dag_longest_path(DG, weight)` | Longest path in DAG |
| `dag_longest_path_length(DG, weight)` | Length of longest path |
| `dag_to_branching(DG)` | Convert DAG to branching |
| `transitive_closure(DG)` | Add all reachable edges |
| `transitive_reduction(DG)` | Remove redundant edges |
| `antichains(DG)` | Generator of antichains |
| `is_aperiodic(DG)` | GCD of cycle lengths == 1? |

---

## Cliques

| Function | Description |
|---|---|
| `find_cliques(G)` | All maximal cliques (Bron-Kerbosch) |
| `find_cliques_recursive(G)` | Recursive variant |
| `make_max_clique_graph(G)` | Graph of maximal cliques |
| `make_clique_bipartite(G)` | Bipartite node-clique graph |
| `graph_clique_number(G)` | Size of largest clique |
| `graph_number_of_cliques(G)` | Count of maximal cliques |
| `node_clique_number(G, v)` | Largest clique containing v |
| `number_of_cliques(G, v)` | Cliques containing v |
| `cliques_containing_node(G, v)` | List of cliques for v |
| `enumerate_all_cliques(G)` | All cliques (all sizes) |
| `max_weight_clique(G, weight)` | Maximum weight clique |

---

## Matching

| Function | Description |
|---|---|
| `max_weight_matching(G, maxcardinality, weight)` | Max weight matching |
| `maximum_matching(G)` | Max cardinality matching |
| `min_weight_matching(G, weight)` | Min weight matching |
| `is_matching(G, matching)` | Valid matching? |
| `is_perfect_matching(G, matching)` | Perfect matching? |
| `is_maximal_matching(G, matching)` | Maximal matching? |

---

## Clustering and Triangles

| Function | Description |
|---|---|
| `triangles(G, nodes)` | Number of triangles per node |
| `clustering(G, nodes, weight)` | Local clustering coefficient |
| `average_clustering(G, nodes, weight)` | Mean clustering |
| `transitivity(G)` | 3 × triangles / triads |
| `square_clustering(G, nodes)` | For bipartite-compatible graphs |
| `generalized_degree(G, nodes)` | Histogram of triangle participation |

---

## Graph Operators

| Function | Description |
|---|---|
| `complement(G)` | All non-edges become edges |
| `reverse(G, copy)` | Reverse all directed edges |
| `compose(G, H)` | Union; merge common node attrs |
| `union(G, H)` | Disjoint-node union |
| `disjoint_union(G, H)` | Union with renamed nodes (always disjoint) |
| `intersection(G, H)` | Edges present in both |
| `difference(G, H)` | Edges in G but not H |
| `symmetric_difference(G, H)` | Edges in exactly one |
| `full_join(G, H)` | All edges between G and H added |
| `cartesian_product(G, H)` | (u,v) nodes, standard product edges |
| `tensor_product(G, H)` | Also called categorical/direct product |
| `strong_product(G, H)` | Cartesian + tensor |
| `lexicographic_product(G, H)` | G with each node replaced by H |
| `rooted_product(G, H, root)` | Identified at root |
| `power(G, k)` | Connect nodes reachable in ≤ k steps |
| `corona_product(G, H)` | Each node of G gets a copy of H |
| `modular_product(G, H)` | Used in subgraph isomorphism |
| `contracted_edge(G, edge, self_loops)` | Merge two nodes |
| `contracted_nodes(G, u, v)` | Merge u into v |
| `quotient_graph(G, partition)` | Aggregate nodes into super-nodes |

---

## Distance Measures

| Function | Description |
|---|---|
| `eccentricity(G, v, weight)` | Max shortest path from v |
| `diameter(G, e, usebounds)` | Max eccentricity |
| `radius(G, e, usebounds)` | Min eccentricity |
| `center(G, e, usebounds)` | Nodes with min eccentricity |
| `periphery(G, e, usebounds)` | Nodes with max eccentricity |
| `barycenter(G, weight)` | Nodes minimizing sum of distances |
| `resistance_distance(G, nodeA, nodeB)` | Effective electrical resistance |
| `kemeny_constant(G, weight)` | Mean hitting time |

---

## Link Analysis

| Function | Description |
|---|---|
| `pagerank(G, alpha, personalization, weight)` | Google PageRank |
| `pagerank_numpy(G, alpha, weight)` | NumPy PageRank |
| `hits(G, max_iter, tol, normalized)` | (hubs, authorities) dicts |
| `hits_numpy(G, normalized)` | NumPy HITS |
| `hits_scipy(G, max_iter, tol, normalized)` | SciPy HITS |

---

## Link Prediction

All return generators of `(u, v, score)` tuples.

| Function | Description |
|---|---|
| `resource_allocation_index(G, ebunch)` | Sum of 1/deg(w) over common neighbors |
| `jaccard_coefficient(G, ebunch)` | Common neighbors / union |
| `adamic_adar_index(G, ebunch)` | Weighted common neighbors |
| `preferential_attachment(G, ebunch)` | deg(u) × deg(v) |
| `cn_soundarajan_hopcroft(G, ebunch, community)` | Community-aware common neighbors |
| `ra_index_soundarajan_hopcroft(G, ebunch, community)` | Community-aware RA |
| `within_inter_cluster(G, ebunch, delta, community)` | Within/between cluster ratio |
| `common_neighbor_centrality(G, ebunch, alpha)` | CCPA index |

---

## Components

(See also Connectivity section above)

| Function | Description |
|---|---|
| `number_weakly_connected_components(DG)` | Count |
| `is_semiconnected(DG)` | Path from every node to at least one other |
| `is_attracting_component(DG, scc)` | No out-edges from SCC |
| `attracting_components(DG)` | SCCs with no out-edges |
| `number_attracting_components(DG)` | Count |
| `k_edge_components(G, k)` | k-edge-connected components |
| `k_node_components(G, k)` | k-node-connected components |

---

## Bipartite Algorithms

Access via `from networkx.algorithms import bipartite`.

| Function | Description |
|---|---|
| `bipartite.is_bipartite(G)` | Test bipartiteness |
| `bipartite.sets(G, top_nodes)` | (top_nodes, bottom_nodes) |
| `bipartite.projected_graph(B, nodes)` | One-mode projection |
| `bipartite.weighted_projected_graph(B, nodes)` | With co-occurrence weights |
| `bipartite.collaboration_weighted_projected_graph(B, nodes)` | Newman's variant |
| `bipartite.overlap_weighted_projected_graph(B, nodes)` | Overlap weight |
| `bipartite.generic_weighted_projected_graph(B, nodes, weight_function)` | Custom weight |
| `bipartite.maximum_matching(B)` | Max matching in bipartite graph |
| `bipartite.minimum_weight_full_matching(B)` | Min weight perfect matching |
| `bipartite.density(B, nodes)` | Density within bipartite graph |
| `bipartite.degrees(B, nodes)` | (top_degree, bottom_degree) dicts |
| `bipartite.betweenness_centrality(B, nodes)` | Bipartite betweenness |
| `bipartite.closeness_centrality(B, nodes)` | Bipartite closeness |
| `bipartite.degree_centrality(B, nodes)` | Bipartite degree centrality |
| `bipartite.clustering(B, nodes)` | Bipartite clustering |
| `bipartite.average_clustering(B, nodes)` | Mean bipartite clustering |
| `bipartite.biadjacency_matrix(B, row_order)` | Sparse biadjacency matrix |
| `bipartite.from_biadjacency_matrix(A)` | Graph from biadjacency matrix |

---

## Coloring

| Function | Description |
|---|---|
| `coloring.greedy_color(G, strategy)` | Greedy vertex coloring |
| `coloring.equitable_color(G, num_colors)` | Equitable coloring |
| `coloring.is_valid_vertex_coloring(G, coloring)` | Validate coloring |

**Strategies for `greedy_color`:**
`largest_first`, `smallest_last`, `random_sequential`, `DSATUR` (saturation-largest-first), `independent_set`, `connected_sequential_bfs`, `connected_sequential_dfs`, `connected_sequential`

---

## Isomorphism

| Function | Description |
|---|---|
| `is_isomorphic(G1, G2, node_match, edge_match)` | Graph isomorphism (VF2++) |
| `could_be_isomorphic(G1, G2)` | Fast inexact check |
| `fast_could_be_isomorphic(G1, G2)` | Faster inexact check |
| `faster_could_be_isomorphic(G1, G2)` | Fastest inexact check |
| `vf2pp_is_isomorphic(G1, G2)` | VF2++ algorithm directly |
| `vf2pp_isomorphisms(G1, G2)` | Generator of isomorphism mappings |
| `vf2pp_all_isomorphisms(G1, G2)` | All mappings |
| `is_subtree_isomorphic(T1, T2)` | Subtree isomorphism |

For subgraph isomorphism use `GraphMatcher`:
```python
from networkx.algorithms import isomorphism
GM = isomorphism.GraphMatcher(G, subgraph)
GM.subgraph_is_isomorphic()
list(GM.subgraph_isomorphisms_iter())
```

---

## Cores and Degeneracy

| Function | Description |
|---|---|
| `core_number(G)` | {node: core_number} |
| `k_core(G, k)` | Subgraph where all nodes have degree ≥ k |
| `k_shell(G, k)` | Nodes in k-core but not (k+1)-core |
| `k_crust(G, k)` | Nodes not in k-core |
| `k_corona(G, k)` | k-core nodes with exactly k neighbors in k-core |
| `k_truss(G, k)` | Edges in at least k-2 triangles |
| `onion_decomposition(G)` | Onion layer for each node |
| `degeneracy_ordering(G)` | Nodes ordered by degeneracy |

---

## Planarity

| Function | Description |
|---|---|
| `is_planar(G)` | (is_planar, embedding) tuple |
| `check_planarity(G, counterexample)` | (is_planar, embedding) |
| `is_kuratowski_subgraph(G)` | Has K5 or K3,3 subdivision? |
| `planar_layout(G, scale, center, dim)` | Position nodes for planar drawing |

---

## Small World Measures

| Function | Description |
|---|---|
| `sigma(G, niter, nrand, seed)` | Sigma coefficient (>1 = small world) |
| `omega(G, niter, nrand, seed)` | Omega coefficient (0 = small world) |

---

## Other Algorithms

### Assortativity
```python
nx.degree_assortativity_coefficient(G)
nx.attribute_assortativity_coefficient(G, attribute)
nx.numeric_assortativity_coefficient(G, attribute)
nx.degree_pearson_correlation_coefficient(G)
nx.average_neighbor_degree(G, source, target, weight)
nx.average_degree_connectivity(G, source, target, weight)
```

### Bridges and Cuts
```python
list(nx.bridges(G))
list(nx.local_bridges(G, with_span))
nx.has_bridges(G)
```

### Eulerian
```python
nx.is_eulerian(G)
nx.eulerian_circuit(G, source)
nx.eulerian_path(G, source)
nx.is_semieulerian(G)
nx.eulerize(G)
```

### Dominating Sets
```python
nx.dominating_set(G, start_with)
nx.is_dominating_set(G, nbunch)
```

### Isolates
```python
list(nx.isolates(G))
nx.number_of_isolates(G)
nx.is_isolate(G, n)
```

### Structural Holes (Social Networks)
```python
nx.constraint(G, nodes, weight)          # {node: constraint_score}
nx.effective_size(G, nodes, weight)      # {node: effective_size}
nx.local_constraint(G, u, v, weight)     # scalar
```

### Rich Club
```python
nx.rich_club_coefficient(G, normalized, Q, seed)  # {degree: coefficient}
```

### Reciprocity (DiGraph)
```python
nx.overall_reciprocity(G)
nx.reciprocity(G, nodes)
```

### Graph Hashing
```python
nx.weisfeiler_lehman_graph_hash(G, edge_attr, node_attr, iterations, digest_size)
nx.weisfeiler_lehman_subgraph_hashes(G, edge_attr, node_attr, iterations, digest_size)
```

### Efficiency
```python
nx.global_efficiency(G)
nx.local_efficiency(G)
```

### Vitality
```python
nx.closeness_vitality(G, node, weight, voronoi_cells)
```

### Voronoi Cells
```python
nx.voronoi_cells(G, center_nodes, weight)
```
