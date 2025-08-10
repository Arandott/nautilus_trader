"""
Generate a sequence diagram for FactorExp-Nautilus integration.

This script creates a visual representation of the call flow
from market data to trading signals.
"""

def generate_mermaid_sequence():
    """Generate Mermaid sequence diagram code."""
    
    diagram = """
sequenceDiagram
    participant Market as Market Data
    participant DE as DataEngine
    participant FEI as FactorExpIndicator
    participant Parser as ExpressionParser
    participant Validator as Validator
    participant Engine as ComputationEngine
    participant Bridge as StreamingBridge
    participant Op20 as StreamingMean(20)
    participant Op50 as StreamingMean(50)
    participant Strategy as Strategy
    participant EE as ExecutionEngine
    
    Note over Market,EE: Initialization Phase
    
    Strategy->>+FEI: new FactorExpIndicator(expression)
    FEI->>+Parser: parse(expression)
    Parser-->>-FEI: AST
    FEI->>+Validator: validate(AST)
    Validator-->>-FEI: ValidationResult
    FEI->>Engine: new ComputationEngine()
    FEI->>Bridge: setup streaming operators
    Strategy->>DE: register_indicator(FEI)
    
    Note over Market,EE: Runtime Phase - Per Bar
    
    Market->>+DE: new Bar(OHLCV)
    DE->>+FEI: handle_bar(bar)
    FEI->>FEI: extract features
    Note right of FEI: data = {close: 45100}
    
    FEI->>FEI: update buffers
    Note right of FEI: count++
    
    alt count >= period
        FEI->>+Engine: compute(expression, data)
        Engine->>Engine: expression.accept(self)
        
        Note over Engine,Op50: Recursive AST Traversal
        
        Engine->>+Op20: update(45100)
        Op20->>Op20: buffer.append()
        Op20->>Op20: compute mean
        Op20-->>-Engine: 45050.0
        
        Engine->>+Op50: update(45100)
        Op50->>Op50: buffer.append()
        Op50->>Op50: compute mean
        Op50-->>-Engine: 44900.0
        
        Engine->>Engine: 45050/44900 = 1.00334
        Engine->>Engine: (1.00334 - 1) * 100
        Engine->>Engine: + log(vol_ratio) * sign(delta)
        
        Engine-->>-FEI: signal = 0.425
    end
    
    FEI-->>-Strategy: value updated
    
    Strategy->>Strategy: on_bar() logic
    Note right of Strategy: if signal > 0.5
    
    opt Entry Signal
        Strategy->>+EE: submit_order(BUY)
        EE-->>-Strategy: order submitted
    end
    
    Note over Market,EE: Process repeats for each bar
"""
    
    return diagram


def generate_component_diagram():
    """Generate component interaction diagram."""
    
    diagram = """
graph TB
    subgraph "Market Data Layer"
        MD[Market Data Feed]
        Bar[Bar Objects]
    end
    
    subgraph "Nautilus Core"
        DE[DataEngine]
        Cache[Cache]
        EE[ExecutionEngine]
    end
    
    subgraph "FactorExp Integration"
        FEI[FactorExpIndicator]
        
        subgraph "Expression Layer"
            Parser[Parser]
            Validator[Validator]
            AST[AST Nodes]
        end
        
        subgraph "Computation Layer"
            Engine[ComputationEngine]
            Bridge[StreamingBridge]
            
            subgraph "Operators"
                Mean[StreamingMean]
                Std[StreamingStd]
                Delta[StreamingDelta]
            end
        end
    end
    
    subgraph "Strategy Layer"
        Strategy[Trading Strategy]
        Signals[Signal Generation]
        Orders[Order Management]
    end
    
    MD --> Bar
    Bar --> DE
    DE --> FEI
    
    FEI --> Parser
    Parser --> AST
    AST --> Validator
    AST --> Engine
    
    Engine --> Bridge
    Bridge --> Mean
    Bridge --> Std
    Bridge --> Delta
    
    Engine --> Signals
    Signals --> Strategy
    Strategy --> Orders
    Orders --> EE
    
    style FEI fill:#f9f,stroke:#333,stroke-width:4px
    style Engine fill:#bbf,stroke:#333,stroke-width:2px
"""
    
    return diagram


if __name__ == "__main__":
    print("=== Sequence Diagram ===")
    print(generate_mermaid_sequence())
    print("\n=== Component Diagram ===")
    print(generate_component_diagram())
    
    # Save to files for rendering
    with open("factorexp_sequence.mmd", "w") as f:
        f.write(generate_mermaid_sequence())
    
    with open("factorexp_components.mmd", "w") as f:
        f.write(generate_component_diagram())
    
    print("\nDiagrams saved to factorexp_sequence.mmd and factorexp_components.mmd")
    print("Use https://mermaid.live to render these diagrams")