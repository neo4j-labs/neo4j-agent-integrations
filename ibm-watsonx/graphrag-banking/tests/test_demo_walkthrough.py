"""Unit tests for demo_walkthrough's step list and proof formatting. None need a
tenant or a database."""

from graphrag_banking import demo_walkthrough as demo


class FakeNode:
    def __init__(self, element_id: str, labels: set[str], **props: object) -> None:
        self.element_id = element_id
        self.labels = labels
        self._props = props

    def keys(self):
        return self._props.keys()

    def __getitem__(self, key: str) -> object:
        return self._props[key]


class FakeRel:
    def __init__(self, element_id: str, type_: str, start_node: FakeNode) -> None:
        self.element_id = element_id
        self.type = type_
        self.start_node = start_node


class FakePath:
    def __init__(self, nodes: list[FakeNode], relationships: list[FakeRel]) -> None:
        self.nodes = nodes
        self.relationships = relationships


CUSTOMER = FakeNode("n1", {"Customer"}, customer_id="C-1001", name="Marcus Chen")
ACCOUNT = FakeNode("n2", {"Account"}, account_id="A-2001", nickname="Main")
WIRE = FakeNode(
    "n3", {"Transaction"}, transaction_id="T-9001", amount=5000.0, status="HELD"
)
PRODUCT = FakeNode("n4", {"AccountProduct"}, product_code="CHK-PREM", name="Premium")
FEE = FakeNode("n5", {"FeeRule"}, rule_code="FEE-WIRE-OUT", amount=30.0)
CHUNK = FakeNode("n6", {"Chunk", "CustomerChunk"}, index=3, text="...")


def test_steps_has_eleven_numbered_in_order():
    assert [s.number for s in demo.STEPS] == list(range(1, 12))
    assert demo.STEPS[-1].title == "The proof in Neo4j Aura"
    assert demo.STEPS[-1].run is demo.step_proof


def test_parse_steps_accepts_step_eleven():
    assert demo.parse_steps("11") == [11]
    assert demo.parse_steps("10-11") == [10, 11]


def test_node_label_customer_shows_id_and_name():
    assert demo.node_label(CUSTOMER) == "C-1001 Marcus Chen"


def test_node_label_transaction_shows_amount_and_status():
    assert demo.node_label(WIRE) == "T-9001 ($5,000.00, HELD)"


def test_node_label_chunk_shows_index():
    assert demo.node_label(CHUNK) == "policy chunk 3"


def test_node_label_uses_natural_key():
    assert demo.node_label(ACCOUNT) == "A-2001"
    assert demo.node_label(PRODUCT) == "CHK-PREM"
    assert demo.node_label(FEE) == "FEE-WIRE-OUT"
    alert = FakeNode("n7", {"ComplianceAlert"}, alert_id="AL-1", rule_code="CMP-1")
    assert demo.node_label(alert) == "AL-1"
    counterparty = FakeNode("n8", {"Counterparty"}, name="Acme Corp")
    assert demo.node_label(counterparty) == "Acme Corp"


def test_node_label_unknown_node():
    assert demo.node_label(FakeNode("n9", {"Other"}, colour="blue")) == "?"


def test_path_line_forward_links():
    path = FakePath(
        [CUSTOMER, ACCOUNT, WIRE],
        [FakeRel("r1", "HOLDS", CUSTOMER), FakeRel("r2", "HAS_TRANSACTION", ACCOUNT)],
    )
    assert demo.path_line(path) == (
        "C-1001 Marcus Chen -[HOLDS]-> A-2001 -[HAS_TRANSACTION]-> "
        "T-9001 ($5,000.00, HELD)"
    )


def test_path_line_backward_link():
    path = FakePath(
        [PRODUCT, FEE, CHUNK],
        [FakeRel("r3", "WAIVED_FOR", FEE), FakeRel("r4", "FROM_CHUNK", FEE)],
    )
    assert demo.path_line(path) == (
        "CHK-PREM <-[WAIVED_FOR]- FEE-WIRE-OUT -[FROM_CHUNK]-> policy chunk 3"
    )


def test_path_line_single_node():
    assert demo.path_line(FakePath([ACCOUNT], [])) == "A-2001"


def test_unique_paths_skips_nulls_and_repeats():
    product = FakePath([ACCOUNT, PRODUCT], [FakeRel("r5", "IS_PRODUCT", ACCOUNT)])
    same_product = FakePath([ACCOUNT, PRODUCT], [FakeRel("r5", "IS_PRODUCT", ACCOUNT)])
    fee = FakePath([PRODUCT, FEE], [FakeRel("r3", "WAIVED_FOR", FEE)])
    records = [
        {"product": product, "fee_waivers": None},
        {"product": same_product, "fee_waivers": fee},
    ]
    assert demo.unique_paths(records, "product") == [product]
    assert demo.unique_paths(records, "fee_waivers") == [fee]
