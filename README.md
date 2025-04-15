# Defending crosstalk-mediated quantum attacks using dynamical decoupling

This repository contains a quantum experiment simulation using Qiskit on IBM Quantum backend. The script initializes a quantum environment, loads experiment configurations as the choice of the user, and runs various attack scenarios to analyze fidelities. For more details regarding the experiment, refer to [Defending crosstalk-mediated quantum attacks using dynamical decoupling](https://arxiv.org/abs/2409.14598).

## Requirements

Ensure you have the following installed:

- Python 3.8+
- Qiskit
- Qiskit IBM Runtime
- NumPy
- Matplotlib
- Jupyter Notebook

You can install the dependencies using:
```sh
pip install qiskit qiskit-ibm-runtime numpy matplotlib jupyter
```

## Setup

1. Clone this repository:
   ```sh
   git clone https://github.com/yourusername/quantum-experiment.git
   cd quantum-experiment
   ```
2. Configure your IBM Quantum account:
   ```python
   from qiskit_ibm_runtime import QiskitRuntimeService
   QiskitRuntimeService.save_account(channel="ibm_quantum", token="YOUR_IBM_TOKEN", overwrite=True, set_as_default=True)
   ```
3. Ensure the `config.json` file exists. If missing, the script will generate a default one that needs to be updated.

## Usage

Use the jupyter notebook:
```sh
TestCircuitQualityDegradation.ipynb
```
The script will prompt you to choose different attack scenarios. Enter `Yes` or `No` accordingly.

## Output

- The experiment results (fidelities) are plotted using Matplotlib.
- Results are stored in JSON files:
  - `ExperimentResult_Count.json` (circuit counts)
  - `ExperimentResult_Fidelities.json` (fidelity values)

## File Structure
```
.
├── TestCircuitQualityDegradation.ipynb  # Main interface which helps in executing the menu for selecting required scenarios
├── config.json    # Configuration file (create/update before running the code)
├── ExperimentClass.py  # Experiment class implementation with code of all the scenarios
```

## Contributing
Feel free to open an issue or submit a pull request to improve the experiment! 🚀

For queries, contact: devikamhr5@gmail.com
