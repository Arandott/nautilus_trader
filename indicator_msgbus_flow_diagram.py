"""
Create a visual diagram showing how indicators receive data in Nautilus Trader.

This script generates a Mermaid diagram illustrating the data flow from
DataEngine to indicators, clarifying the role of MessageBus and Strategy.
"""

def generate_data_flow_diagram():
    """Generate Mermaid diagram for indicator data flow."""
    
    diagram = """
graph LR
    %% Nodes
    MD[Market Data Source]
    DE[DataEngine]
    MB[MessageBus]
    ST[Strategy/Actor]
    IND1[Indicator 1]
    IND2[Indicator 2]
    IND3[Indicator N]
    
    %% Styling
    classDef dataSource fill:#f9f,stroke:#333,stroke-width:2px
    classDef engine fill:#bbf,stroke:#333,stroke-width:2px
    classDef msgbus fill:#bfb,stroke:#333,stroke-width:2px
    classDef strategy fill:#fbf,stroke:#333,stroke-width:4px
    classDef indicator fill:#fbb,stroke:#333,stroke-width:2px
    
    class MD dataSource
    class DE engine
    class MB msgbus
    class ST strategy
    class IND1,IND2,IND3 indicator
    
    %% Connections
    MD -->|Bar data| DE
    DE -->|_handle_bar| DE
    DE -->|publish 'data.bars.{type}'| MB
    MB -->|notify subscribers| ST
    ST -->|handle_bar| ST
    
    %% Internal Strategy Flow
    ST -->|for ind in _indicators_for_bars| IND1
    ST -->|indicator.handle_bar(bar)| IND2
    ST -->|direct method call| IND3
    
    %% Annotations
    DE -.- DEPUB[/"self._msgbus.publish_c(topic, bar)"/]
    ST -.- STSUB[/"Already subscribed via<br/>subscribe_bars()"/]
    ST -.- STREG[/"Indicators registered via<br/>register_indicator_for_bars()"/]
    
    style DEPUB fill:#fff,stroke:#666,stroke-dasharray: 5 5
    style STSUB fill:#fff,stroke:#666,stroke-dasharray: 5 5
    style STREG fill:#fff,stroke:#666,stroke-dasharray: 5 5
"""
    
    return diagram


def generate_registration_flow():
    """Generate diagram showing indicator registration process."""
    
    diagram = """
sequenceDiagram
    participant S as Strategy
    participant A as Actor Base
    participant MB as MessageBus
    participant DE as DataEngine
    
    Note over S,DE: Registration Phase
    
    S->>A: register_indicator_for_bars(bar_type, indicator)
    A->>A: Add to _indicators_for_bars[bar_type]
    Note right of A: No MessageBus interaction!
    
    S->>MB: subscribe_bars(bar_type)
    MB->>MB: Register handler for topic
    Note right of MB: topic = "data.bars.{bar_type}"
    
    Note over S,DE: Runtime Phase
    
    DE->>MB: publish("data.bars.{bar_type}", bar)
    MB->>S: handle_bar(bar)
    S->>A: Inherited handle_bar method
    A->>A: indicators = _indicators_for_bars.get(bar_type)
    
    loop For each indicator
        A->>A: indicator.handle_bar(bar)
    end
    
    Note over A: Direct method calls,<br/>no MessageBus involved
"""
    
    return diagram


def generate_comparison_diagram():
    """Generate diagram comparing actual vs. assumed architecture."""
    
    diagram = """
graph TB
    subgraph "Assumed Architecture (INCORRECT)"
        DE1[DataEngine] -->|publish| MB1[MessageBus]
        MB1 -->|subscribe| IND1A[Indicator A]
        MB1 -->|subscribe| IND1B[Indicator B]
        MB1 -->|subscribe| IND1C[Indicator C]
        MB1 -->|subscribe| ST1[Strategy]
    end
    
    subgraph "Actual Architecture (CORRECT)"
        DE2[DataEngine] -->|publish| MB2[MessageBus]
        MB2 -->|subscribe<br/>ONLY| ST2[Strategy]
        ST2 -->|direct call| IND2A[Indicator A]
        ST2 -->|direct call| IND2B[Indicator B]
        ST2 -->|direct call| IND2C[Indicator C]
    end
    
    style ST1 fill:#faa
    style ST2 fill:#afa,stroke:#333,stroke-width:4px
"""
    
    return diagram


if __name__ == "__main__":
    print("=== Data Flow Diagram ===")
    print(generate_data_flow_diagram())
    
    print("\n=== Registration & Runtime Flow ===")
    print(generate_registration_flow())
    
    print("\n=== Architecture Comparison ===")
    print(generate_comparison_diagram())
    
    # Save diagrams
    with open("indicator_data_flow.mmd", "w") as f:
        f.write(generate_data_flow_diagram())
    
    with open("indicator_registration_flow.mmd", "w") as f:
        f.write(generate_registration_flow())
    
    with open("indicator_architecture_comparison.mmd", "w") as f:
        f.write(generate_comparison_diagram())
    
    print("\nDiagrams saved to .mmd files")
    print("Use https://mermaid.live to render these diagrams")