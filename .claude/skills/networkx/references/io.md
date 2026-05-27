# NetworkX File I/O Reference

Format guide for reading and writing graphs. All functions in `nx` namespace.
Full docs: https://networkx.org/documentation/stable/reference/readwrite/index.html

---

## Format Comparison

| Format | Extension | Preserves Attrs | Directed | Human Readable | Best For |
|---|---|---|---|---|---|
| GraphML | `.graphml` | Yes | Yes | Yes (XML) | Cross-tool exchange (Gephi, yEd, Cytoscape) |
| GML | `.gml` | Yes | Yes | Yes | Simple export, human inspection |
| GEXF | `.gexf` | Yes | Yes | Yes (XML) | Gephi (supports dynamic/temporal graphs) |
| Pajek | `.net` | Partial | Yes | Yes | Pajek software |
| Edge list | `.txt`, `.csv` | Weight only | Implicit | Yes | Simple pipelines, weight-only graphs |
| Adjacency list | `.txt` | No | No | Yes | Unweighted graphs, small datasets |
| JSON (node-link) | `.json` | Yes | Yes | Yes | Web apps, D3.js, Cytoscape.js |
| JSON (adjacency) | `.json` | Yes | Yes | Yes | Compact JSON alternative |
| Graph6/Sparse6 | `.g6`, `.s6` | No | No | No | Compact, canonical, combinatorics tools |
| LEDA | `.leda` | Partial | Yes | Yes | LEDA software (read-only) |

---

## GraphML (Recommended for Cross-Tool Use)

```python
nx.write_graphml(G, "graph.graphml")
nx.write_graphml(G, "graph.graphml", encoding="utf-8", prettyprint=True)

G = nx.read_graphml("graph.graphml")
G = nx.read_graphml("graph.graphml", node_type=str)   # force string node IDs
G = nx.read_graphml("graph.graphml", edge_key_type=int)

# Generate GraphML string (no file)
s = "\n".join(nx.generate_graphml(G))
```

GraphML preserves all node and edge attributes. Node IDs must be strings in the XML.

---

## GML

```python
nx.write_gml(G, "graph.gml")
nx.write_gml(G, "graph.gml", stringizer=str)   # custom attribute serializer

G = nx.read_gml("graph.gml")
G = nx.read_gml("graph.gml", label="id")        # use "id" field as node label
G = nx.read_gml("graph.gml", destringizer=int)  # convert node labels

# From/to string
gml_str = "\n".join(nx.generate_gml(G))
G = nx.parse_gml(gml_str)
```

GML supports nested attributes. Attribute values must be int, float, str, list, or dict.

---

## GEXF (Gephi)

```python
nx.write_gexf(G, "graph.gexf")
nx.write_gexf(G, "graph.gexf", encoding="utf-8", prettyprint=True, version="1.2draft")

G = nx.read_gexf("graph.gexf")
G = nx.read_gexf("graph.gexf", node_type=str, relabel=False)
G = nx.read_gexf("graph.gexf", relabel=True)   # use "label" attr as node ID
```

GEXF supports dynamic (temporal) attributes with `start`/`end` timestamps.

---

## Edge List

```python
# Write
nx.write_edgelist(G, "edges.txt")
nx.write_edgelist(G, "edges.txt", comments="#", delimiter=" ", data=True)
nx.write_edgelist(G, "edges.txt", data=["weight", "color"])   # specific attrs only

# Read
G = nx.read_edgelist("edges.txt")
G = nx.read_edgelist("edges.txt",
                      comments="#",
                      delimiter=",",
                      nodetype=int,              # parse node IDs as int
                      data=[("weight", float)],  # parse weight column
                      create_using=nx.DiGraph)

# Weighted shorthand (3rd column = weight)
nx.write_weighted_edgelist(G, "edges.txt")
G = nx.read_weighted_edgelist("edges.txt", nodetype=int)

# From a string or iterator
lines = ["1 2", "2 3", "3 4"]
G = nx.parse_edgelist(lines, nodetype=int)
G = nx.parse_edgelist(lines, data=[("weight", float)])
```

---

## Adjacency List

Stores only topology (no edge attributes).

```python
nx.write_adjlist(G, "adj.txt")
nx.write_adjlist(G, "adj.txt", comments="#", delimiter=" ", encoding="utf-8")

G = nx.read_adjlist("adj.txt")
G = nx.read_adjlist("adj.txt", comments="#", delimiter=" ", nodetype=int,
                    create_using=nx.DiGraph)

# Multiline variant (edge data on separate lines)
nx.write_multiline_adjlist(G, "adj_multi.txt")
G = nx.read_multiline_adjlist("adj_multi.txt", nodetype=int,
                               data=[("weight", float)])

# From string iterator
lines = ["1 2 3", "2 4 5", "3"]
G = nx.parse_adjlist(lines, nodetype=int)
```

---

## Pajek

```python
nx.write_pajek(G, "graph.net")
G = nx.read_pajek("graph.net")
G = nx.read_pajek("graph.net", encoding="utf-8")

# From string
pajek_str = "..."
G = nx.parse_pajek(pajek_str)

# DiGraph
DG = nx.read_pajek("directed.net")
```

Pajek format supports node coordinates and partition data via `x`, `y` attributes.

---

## JSON Formats

### Node-Link (Most Compatible)

```python
from networkx.readwrite import json_graph
import json

# Write
data = json_graph.node_link_data(G)
with open("graph.json", "w") as f:
    json.dump(data, f, indent=2)

# Read
with open("graph.json") as f:
    data = json.load(f)
G = json_graph.node_link_graph(data)
G = json_graph.node_link_graph(data, directed=True, multigraph=False)

# Quick generation
s = json_graph.node_link_data(G)  # dict ready for JSON serialization
```

### Adjacency JSON

```python
data = json_graph.adjacency_data(G)
G = json_graph.adjacency_graph(data)
```

### Cytoscape JSON (for Cytoscape.js)

```python
data = json_graph.cytoscape_data(G)
G = json_graph.cytoscape_graph(data)
```

### Tree JSON (for tree-structured graphs)

```python
data = json_graph.tree_data(G, root=0)
G = json_graph.tree_graph(data)
```

---

## Pandas Integration

```python
import pandas as pd

# From edge list DataFrame
df = pd.DataFrame({"source": [1, 2, 3], "target": [2, 3, 1],
                    "weight": [1.0, 0.5, 0.8], "color": ["red","blue","green"]})
G = nx.from_pandas_edgelist(df,
                              source="source",
                              target="target",
                              edge_attr=True,       # include all remaining cols
                              create_using=nx.DiGraph)
# edge_attr can also be a list: edge_attr=["weight", "color"]

# To edge list DataFrame
df = nx.to_pandas_edgelist(G, source="from", target="to")

# From adjacency matrix DataFrame
adj_df = pd.DataFrame([[0,1,0],[1,0,1],[0,1,0]],
                       index=["a","b","c"], columns=["a","b","c"])
G = nx.from_pandas_adjacency(adj_df)
G = nx.from_pandas_adjacency(adj_df, create_using=nx.DiGraph)

# To adjacency DataFrame
adj_df = nx.to_pandas_adjacency(G, weight="weight", dtype=float)
```

---

## NumPy / SciPy Integration

```python
import numpy as np
from scipy import sparse

# NumPy adjacency matrix
A = nx.to_numpy_array(G, nodelist=sorted(G), weight="weight", dtype=float)
G = nx.from_numpy_array(A)
G = nx.from_numpy_array(A, create_using=nx.DiGraph, parallel_edges=False)

# Get node ordering used
nodelist = sorted(G)  # must match what you passed to to_numpy_array

# SciPy sparse (for large graphs)
S = nx.to_scipy_sparse_array(G, format="csr", weight="weight", dtype=float)
G = nx.from_scipy_sparse_array(S, create_using=nx.DiGraph)

# Laplacian matrix
L = nx.laplacian_matrix(G, weight="weight")          # scipy sparse
L = nx.normalized_laplacian_matrix(G, weight="weight")
L = nx.directed_laplacian_matrix(G)
L = nx.adjacency_matrix(G, weight="weight")           # scipy sparse adjacency
```

---

## Network Text (Debug/Display)

```python
# Print to stdout
nx.write_network_text(G)
nx.write_network_text(G, path=sys.stdout, with_labels=True,
                      sources=[start_node], max_depth=5)

# Capture as string
import io
buf = io.StringIO()
nx.write_network_text(G, path=buf)
text = buf.getvalue()
```

---

## Graph6 / Sparse6 (Compact Canonical Format)

```python
# Graph6 (small undirected graphs, ≤ ~62 nodes)
nx.write_graph6(G, "graph.g6")
G_list = list(nx.read_graph6("graph.g6"))   # returns generator

# Single graph from string
G = nx.from_graph6_bytes(b"IsP@OkWHG")

# Sparse6 (larger sparse undirected graphs)
nx.write_sparse6(G, "graph.s6")
G_list = list(nx.read_sparse6("graph.s6"))
```

---

## DOT Format (requires pygraphviz or pydot)

```python
# pygraphviz
A = nx.nx_agraph.to_agraph(G)
A.write("graph.dot")
G = nx.nx_agraph.from_agraph(A)
G = nx.nx_agraph.read_dot("graph.dot")
nx.nx_agraph.write_dot(G, "graph.dot")

# pydot
P = nx.nx_pydot.to_pydot(G)
G = nx.nx_pydot.from_pydot(P)
G = nx.nx_pydot.read_dot("graph.dot")
nx.nx_pydot.write_dot(G, "graph.dot")
```

Install: `pip install pygraphviz` or `pip install pydot`

---

## Common Pitfalls

**Node type changes on read** — most text formats read nodes as strings. Pass `nodetype=int` (or `node_type=int` for GraphML/GEXF) to restore integer IDs.

```python
G = nx.read_edgelist("edges.txt", nodetype=int)
G = nx.read_graphml("graph.graphml", node_type=int)
```

**Directed vs undirected on read** — use `create_using` to force a type:
```python
G = nx.read_edgelist("edges.txt", create_using=nx.DiGraph)
```

**Attribute loss** — edge list and adjacency list formats only preserve weight. Use GraphML or GML to preserve all attributes.

**Large graphs** — prefer SciPy sparse over NumPy for adjacency matrices when the graph has >10k nodes.

**Disconnected graphs and path lengths** — `average_shortest_path_length` raises `NetworkXError` on disconnected graphs. Work on the largest component:
```python
lcc = G.subgraph(max(nx.connected_components(G), key=len)).copy()
```
