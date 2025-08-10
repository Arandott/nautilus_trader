"""
Create visual diagrams illustrating the FactorExp-NT native indicator integration architecture.
"""

def generate_integration_architecture():
    """Generate the main integration architecture diagram."""
    
    diagram = """
graph TB
    subgraph "Current FactorExp Architecture"
        E1[Expression String] --> P1[Parser]
        P1 --> AST1[AST]
        AST1 --> V1[Visitor Pattern]
        V1 --> R1[Python Computation]
    end
    
    subgraph "Proposed Hybrid Architecture"
        E2[Expression String] --> P2[Parser]
        P2 --> AST2[AST]
        AST2 --> OPT[Optimizer]
        OPT --> |Adaptable| NA[Native Adapter]
        OPT --> |Custom| FE[FactorExp Engine]
        NA --> NT[NT Native Indicators<br/>Rust/Cython]
        FE --> PC[Python Computation]
        NT --> R2[Result]
        PC --> R2
    end
    
    style NT fill:#afa,stroke:#333,stroke-width:3px
    style NA fill:#aaf,stroke:#333,stroke-width:2px
    style OPT fill:#faa,stroke:#333,stroke-width:2px
"""
    
    return diagram


def generate_performance_layers():
    """Show the performance characteristics of different layers."""
    
    diagram = """
graph LR
    subgraph "Performance Hierarchy"
        R[Rust Core<br/>100x] --> C[Cython Binding<br/>10-50x]
        C --> P[Pure Python<br/>1x baseline]
    end
    
    subgraph "FactorExp Integration Points"
        FE1[Native Mapping<br/>Full Rust Speed] --> R
        FE2[Cython Operators<br/>Medium Speed] --> C
        FE3[Python Engine<br/>Baseline] --> P
    end
    
    style R fill:#4a4,stroke:#333,stroke-width:3px
    style C fill:#aa4,stroke:#333,stroke-width:2px
    style P fill:#a44,stroke:#333,stroke-width:1px
"""
    
    return diagram


def generate_adapter_flow():
    """Show how the adapter pattern works."""
    
    diagram = """
sequenceDiagram
    participant User
    participant FEI as FactorExpIndicator
    participant AE as AdapterEngine
    participant NA as NativeAdapter
    participant NT as NT Indicator
    participant FE as FactorExp Engine
    
    User->>FEI: Create("TS_Mean($close, 20)")
    FEI->>FEI: Parse expression
    FEI->>AE: Can adapt this expression?
    
    alt Expression is adaptable
        AE->>NA: Create adapter
        NA->>NT: Create SimpleMovingAverage(20)
        NA-->>FEI: Return native indicator
        Note right of FEI: Use native indicator<br/>for all computations
        
        loop On each update
            User->>FEI: update_raw(value)
            FEI->>NT: update_raw(value)
            NT-->>FEI: Computed result
        end
        
    else Expression not adaptable
        AE-->>FEI: Cannot adapt
        FEI->>FE: Setup FactorExp engine
        Note right of FEI: Use Python engine
        
        loop On each update
            User->>FEI: update_raw(value)
            FEI->>FE: compute(value)
            FE-->>FEI: Computed result
        end
    end
"""
    
    return diagram


def generate_optimization_strategy():
    """Show the optimization decision tree."""
    
    diagram = """
graph TD
    E[Expression] --> A{Analyze AST}
    
    A -->|Simple Op| S[Single Operator<br/>e.g., TS_Mean]
    A -->|Composite| C[Multiple Operators<br/>e.g., MA1/MA2]
    A -->|Complex| X[Custom Logic<br/>e.g., If-Then-Else]
    
    S --> S1{Has Native<br/>Equivalent?}
    S1 -->|Yes| SN[Use Native<br/>100% Speed]
    S1 -->|No| SP[Use Python<br/>Baseline]
    
    C --> C1{All Ops<br/>Adaptable?}
    C1 -->|Yes| CN[Full Native<br/>90% Speed]
    C1 -->|Partial| CP[Hybrid Mode<br/>50-70% Speed]
    C1 -->|No| CPY[Pure Python<br/>Baseline]
    
    X --> XP[Python Only<br/>Max Flexibility]
    
    style SN fill:#4f4,stroke:#333,stroke-width:3px
    style CN fill:#4f4,stroke:#333,stroke-width:3px
    style CP fill:#ff4,stroke:#333,stroke-width:2px
"""
    
    return diagram


def generate_implementation_phases():
    """Show the implementation roadmap."""
    
    diagram = """
gantt
    title FactorExp-NT Integration Roadmap
    dateFormat  YYYY-MM-DD
    section Phase 1
    Enable AdapterEngine     :done, p1, 2024-01-01, 7d
    Map Top 5 Operators      :active, p2, after p1, 14d
    Basic Testing            :p3, after p2, 7d
    
    section Phase 2
    Hybrid Computation       :p4, after p3, 21d
    Performance Benchmarks   :p5, after p4, 7d
    Map Next 10 Operators    :p6, after p4, 14d
    
    section Phase 3
    Cython Operators         :p7, after p6, 30d
    Advanced Optimization    :p8, after p7, 21d
    Production Deployment    :p9, after p8, 14d
"""
    
    return diagram


if __name__ == "__main__":
    print("=== Integration Architecture ===")
    print(generate_integration_architecture())
    
    print("\n=== Performance Layers ===")
    print(generate_performance_layers())
    
    print("\n=== Adapter Flow ===")
    print(generate_adapter_flow())
    
    print("\n=== Optimization Strategy ===")
    print(generate_optimization_strategy())
    
    print("\n=== Implementation Phases ===")
    print(generate_implementation_phases())
    
    # Save diagrams
    diagrams = {
        "integration_architecture": generate_integration_architecture(),
        "performance_layers": generate_performance_layers(),
        "adapter_flow": generate_adapter_flow(),
        "optimization_strategy": generate_optimization_strategy(),
        "implementation_phases": generate_implementation_phases(),
    }
    
    for name, content in diagrams.items():
        with open(f"factorexp_nt_{name}.mmd", "w") as f:
            f.write(content)
    
    print("\nDiagrams saved to .mmd files")
    print("Use https://mermaid.live to render these diagrams")