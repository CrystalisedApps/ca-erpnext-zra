### Ca Erpnext Zra

#### Zambia Revenue Authority (ZRA) VSDC API Integration for Frappe/ERPNext

A Frappe custom application that integrates with the Zambia Revenue Authority (ZRA) Virtual Sales Data Controller (VSDC) API to enable seamless tax compliance, e-invoicing, and reporting directly within your ERP system.

This app provides a secure and standardized way for businesses to interact with ZRA’s VSDC platform, ensuring all electronic invoices, receipts, and related tax data are automatically transmitted in compliance with ZRA regulations.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app ca_erpnext_zra
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/ca_erpnext_zra
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

agpl-3.0
