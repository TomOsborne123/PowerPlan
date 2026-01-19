# Project Example Structure (claude)

energy_system_project/
├── src/
│   ├── __init__.py
│   ├── README.md                        # Overview of source code structure
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── README.md                    # API clients documentation
│   │   ├── base.py                      # Base API client class
│   │   ├── met_office.py                # Met Office weather API
│   │   └── energy_market.py             # Energy market price APIs (optional)
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── README.md                    # Data models explanation
│   │   ├── weather.py                   # Weather data models
│   │   ├── energy.py                    # Energy generation/consumption models
│   │   ├── finance.py                   # Financial/cost models
│   │   └── balancing.py                 # Grid balancing models
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── README.md                    # Business logic overview
│   │   ├── forecast_service.py          # Energy forecasting
│   │   ├── balancing_service.py         # Energy balancing logic
│   │   └── finance_service.py           # Financial calculations
│   │
│   ├── data/
│   │   ├── __init__.py
│   │   ├── README.md                    # Data processing documentation
│   │   ├── processors.py                # Data transformation
│   │   ├── validators.py                # Data validation
│   │   └── cache.py                     # API response caching
│   │
│   ├── optimization/
│   │   ├── __init__.py
│   │   ├── README.md                    # Optimization algorithms docs
│   │   ├── energy_optimizer.py          # Energy dispatch optimization
│   │   └── cost_optimizer.py            # Cost minimization
│   │
│   └── utils/
│       ├── __init__.py
│       ├── README.md                    # Utility functions guide
│       ├── logger.py                    # Logging configuration
│       └── helpers.py                   # Utility functions
│
├── config/
│   ├── __init__.py
│   ├── README.md                        # Configuration setup guide
│   ├── settings.py                      # General settings
│   ├── api_config.py                    # API endpoints and keys
│   └── model_config.py                  # Model parameters
│
├── app/
│   ├── __init__.py
│   ├── README.md                        # How to run the application
│   ├── main.py                          # Application entry point
│   ├── routes/                          # If web app
│   │   ├── __init__.py
│   │   ├── energy.py
│   │   └── forecast.py
│   └── cli.py                           # Command-line interface (optional)
│
├── tests/
│   ├── __init__.py
│   ├── README.md                        # Testing guidelines
│   ├── unit/
│   │   ├── test_api/
│   │   │   └── test_met_office.py
│   │   ├── test_models/
│   │   │   ├── test_energy.py
│   │   │   └── test_finance.py
│   │   └── test_services/
│   └── integration/
│       └── test_balancing_workflow.py
│
├── data/                                # Data storage
│   ├── README.md                        # Data directory structure
│   ├── raw/                             # Raw API responses
│   ├── processed/                       # Processed data
│   └── outputs/                         # Model outputs
│
├── notebooks/                           # Jupyter notebooks for analysis
│   ├── README.md                        # Notebooks overview
│   └── exploratory_analysis.ipynb
│
├── docs/
│   └── api_documentation.md
│
├── scripts/
│   ├── README.md                        # Standalone scripts documentation
│   ├── fetch_weather_data.py           # Standalone scripts
│   └── run_balancing_model.py
│
├── .env                                 # Environment variables (not in git)
├── .env.example                         # Template for .env
├── .gitignore
├── requirements.txt                     # Python dependencies
├── setup.py                             # Package setup
└── README.md                            # Main project README


