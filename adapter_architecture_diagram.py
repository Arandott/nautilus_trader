"""
Visualize the AdapterEngine architecture and why it's not currently used.
"""

def generate_adapter_architecture():
    """Generate diagram showing adapter architecture design."""
    
    diagram = """
graph TB
    subgraph "Designed Architecture (Not Active)"
        E1[Expression] --> AP[Adapter Processor]
        AP --> |can_adapt?| AE[AdapterEngine]
        AE --> |Yes| NI[Native Indicator<br/>SMA, EMA, etc.]
        AE --> |No| VP1[Visitor Pattern]
        NI --> R1[Result]
        VP1 --> R1
    end
    
    subgraph "Current Implementation (Active)"
        E2[Expression] --> AST[AST Builder]
        AST --> VP2[Visitor Pattern<br/>Computation]
        VP2 --> R2[Result]
    end
    
    style AP fill:#faa,stroke:#333,stroke-dasharray: 5 5
    style AE fill:#faa,stroke:#333,stroke-dasharray: 5 5
    style NI fill:#faa,stroke:#333,stroke-dasharray: 5 5
    
    style E2 fill:#afa
    style AST fill:#afa
    style VP2 fill:#afa
    style R2 fill:#afa
"""
    
    return diagram


def generate_adapter_registry():
    """Show the adapter registry that exists but isn't used."""
    
    diagram = """
graph LR
    subgraph "Adapter Registry (Implemented but Unused)"
        AR[AdapterEngine]
        AR --> SMA[SMAAdapter<br/>TS_Mean → SimpleMovingAverage]
        AR --> EMA[EMAAdapter<br/>TS_EMA → ExponentialMovingAverage]
        AR --> WMA[WMAAdapter<br/>TS_WMA → WeightedMovingAverage]
        AR --> MIN[MinAdapter<br/>TS_Min → Not Implemented]
        AR --> MAX[MaxAdapter<br/>TS_Max → Not Implemented]
    end
    
    subgraph "Usage Status"
        US[/"No code creates<br/>AdapterEngine instance"/]
        UC[/"No code imports<br/>AdapterEngine class"/]
        UR[/"No code references<br/>adapter functionality"/]
    end
    
    style AR fill:#faa,stroke:#333,stroke-dasharray: 5 5
    style SMA fill:#faa,stroke:#333,stroke-dasharray: 5 5
    style EMA fill:#faa,stroke:#333,stroke-dasharray: 5 5
    style WMA fill:#faa,stroke:#333,stroke-dasharray: 5 5
    style MIN fill:#fcc,stroke:#333,stroke-dasharray: 5 5
    style MAX fill:#fcc,stroke:#333,stroke-dasharray: 5 5
"""
    
    return diagram


def generate_performance_comparison():
    """Show potential performance benefits if adapters were enabled."""
    
    diagram = """
graph TD
    subgraph "Without Adapters (Current)"
        WA1[Parse Expression]
        WA2[Build AST]
        WA3[For each bar:<br/>- Traverse AST<br/>- Execute operators<br/>- Python loops]
        WA1 --> WA2 --> WA3
    end
    
    subgraph "With Adapters (Potential)"
        A1[Parse Expression]
        A2[Check Adapter]
        A3[Create Native Indicator<br/>Once at startup]
        A4[For each bar:<br/>- Direct C/Rust call<br/>- No AST traversal<br/>- Optimized loops]
        A1 --> A2 --> A3 --> A4
    end
    
    P1[/"Performance Impact:<br/>- AST traversal overhead<br/>- Python interpreter cost<br/>- Repeated computations"/]
    P2[/"Performance Benefit:<br/>- One-time setup cost<br/>- Native code execution<br/>- Hardware optimizations"/]
    
    WA3 --> P1
    A4 --> P2
    
    style A2 fill:#aaf
    style A3 fill:#aaf
    style A4 fill:#afa
    style P2 fill:#afa
"""
    
    return diagram


def generate_implementation_path():
    """Show how to enable adapters if needed."""
    
    diagram = """
sequenceDiagram
    participant U as User
    participant FEI as FactorExpIndicator
    participant AE as AdapterEngine
    participant NI as Native Indicator
    participant VP as Visitor Pattern
    
    Note over U,VP: Enabling Adapter Path (Not Implemented)
    
    U->>FEI: Create with expression
    FEI->>FEI: Parse expression to AST
    FEI->>AE: Create AdapterEngine
    FEI->>AE: can_adapt(expression)?
    
    alt Can Adapt
        AE->>NI: Create native indicator
        AE-->>FEI: Return indicator instance
        Note right of FEI: Store and use<br/>native indicator
    else Cannot Adapt
        AE-->>FEI: Return None
        Note right of FEI: Use visitor pattern
    end
    
    Note over U,VP: Runtime Execution
    
    U->>FEI: update_raw(bar)
    alt Using Native Indicator
        FEI->>NI: handle_bar(bar)
        NI-->>FEI: Computed value
    else Using Visitor Pattern
        FEI->>VP: evaluate(ast, data)
        VP-->>FEI: Computed value
    end
"""
    
    return diagram


if __name__ == "__main__":
    print("=== Adapter Architecture Overview ===")
    print(generate_adapter_architecture())
    
    print("\n=== Adapter Registry Status ===")
    print(generate_adapter_registry())
    
    print("\n=== Performance Comparison ===")
    print(generate_performance_comparison())
    
    print("\n=== Implementation Path ===")
    print(generate_implementation_path())
    
    # Save diagrams
    with open("adapter_architecture.mmd", "w") as f:
        f.write(generate_adapter_architecture())
    
    with open("adapter_registry.mmd", "w") as f:
        f.write(generate_adapter_registry())
    
    with open("adapter_performance.mmd", "w") as f:
        f.write(generate_performance_comparison())
    
    with open("adapter_implementation.mmd", "w") as f:
        f.write(generate_implementation_path())
    
    print("\nDiagrams saved to .mmd files")
    print("Use https://mermaid.live to render these diagrams")