### CA ERPNext ZRA Smart Invoice

# Zambia Revenue Authority (ZRA) VSDC Smart Invoice API Integration for Frappe/ERPNext

A Frappe custom application that integrates with the Zambia Revenue Authority (ZRA) Virtual Sales Data Controller (VSDC) API to enable seamless tax compliance, e-invoicing, and reporting directly within your ERP system.

This app provides a secure and standardized way for businesses to interact with ZRA’s VSDC platform, ensuring all electronic invoices, receipts, and related tax data are automatically transmitted in compliance with ZRA regulations.

##  Features
- **Authentication**:The authentication module manages secure access to the **Crystal ZRA Smart Invoice API** using **JWT
-  **Device Initialization** with ZRA Smart Invoice system  
-  Retrieval of **Standard Codes** (classification, VAT, excise, packaging, etc.)  
-  **Item Registration**: save ERPNext items with ZRA Smart API  
- **Sales Management**: Manages the full Sales lifecycle
- **Stock Adjustment**: Handles real-time stock synchronization with ZRA
-  **Background Jobs** for async API calls  
-  **Integration Request Logs** for request/response traceability  



### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app ca_erpnext_zra
# Apply patches and custom fields
bench migrate
```
##  Configuration

Then configure the app inside **ERPNext**:

1. Go to **Crystal ZRA Smart Invoice Settings** in ERPNext  
2. Enter your **TPIN**, **Branch ID (BhfId)**, and **API credentials**  
3. Save and mark settings as **Active**  

---

## Features & Workflow


### 1. Authentication

The authentication module manages secure access to the **Crystal ZRA Smart Invoice API** using **JWT (JSON Web Tokens)**.  
It ensures that all API requests to ZRA are authorized and compliant with security standards.

####  Key Capabilities:
- Automated login using `/api/v1/Users/GetToken`
- Securely stores and refreshes the JWT before expiry
- Injects the `Authorization: Bearer <token>` header into every API request
- Caches tokens in the **Crystal ZRA Smart Invoice Settings** doctype
- Transparent error handling and token renewal

####  Technical Notes:
- Managed via `ZRAAuthService` in `services/auth_service.py`
- Automatically refreshes tokens using per-request validation
- Logs authentication attempts in the **Integration Request** table for traceability


####  Example Response:
```json
{
  "Version": "1.0",
  "StatusCode": 200,
  "IsSuccess": true,
  "Result": {
    "token": "eyJhbGciOiJIUzI1NiIsInR5..."
  }
}
```


### 2. Device Initialization  

Before interacting with ZRA’s Smart Invoice system, the ERPNext instance must be initialized as a registered VSDC device.
This process associates your business TPIN and Branch ID (BhfId) with ZRA’s infrastructure.

- **Endpoint**: `InitializeDevice`  
- **ERPNext DocType**: `Crystal ZRA Smart Invoice Settings`  

![alt text](image-3.png)

---

### 3. Retrieval of Standard Codes  

To correctly classify items, ZRA requires standard codes such as:  

- **Item Classification Codes** (`itemClsCd`)  
- **Item Type Codes** (`itemTyCd`)  
- **Packaging Unit Codes**  
- **Quantity Unit Codes**  
- **VAT / IPL / Levy / Excise Categories**  

These codes are retrieved from the **Smart API** and stored in **custom ERPNext doctypes** for reuse.  

![alt text](image-4.png)

---

### 4. Item Classification Codes  

ERPNext **Items** are linked to **Crystallised Smart doctypes**, where each field references a standard code from ZRA.  

For example:  

- `custom_smart_item_classification_code` → `itemClsCd`  
- `custom_smart_item_type` → `itemTyCd`  
- `custom_smart_country_of_origin` → `orgnNatCd`  
- `custom_smart_packaging_unit_code` → `pkgUnitCd`  
- `custom_smart_quantity_unit_code` → `qtyUnitCd`  



---
![alt text](image-1.png)
### 4. Saving Items (Item Management)  

Once Items are properly configured, they can be **registered with Smart Zambia**.  

#### 🔹 Payload Builder  

We build a **ZRA-compliant payload** from ERPNext Item data.  

**Example Payload**:  

```json
{
  "tpin": "1234567890",
  "bhfId": "01",
  "itemCd": "ITEM-0001",
  "itemClsCd": "101",
  "itemTyCd": "1",
  "itemNm": "Sample Item",
  "itemStdNm": "Sample Standard Name",
  "orgnNatCd": "ZM",
  "pkgUnitCd": "PKG",
  "qtyUnitCd": "EA",
  "taxTyCd": "A",
  "btchNo": "BATCH001",
  "bcd": "8901234567890",
  "dftPrc": 100.0,
  "addInfo": "Test item for Smart Invoice registration"
}
```
---
 Once submitted, the system will:  

- Enqueue the request in **Frappe background jobs**  
- Send the payload to **Crystal VSDC API**  
- Log request/response in the **Integration Request doctype**  
- Mark the Item as **registered** upon success  
---

### 5. Sales Management
Manages the full Sales Record (SAR) lifecycle: saving and issuing invoices through the ZRA Smart Invoice system.

#### Key Capabilities:

-Automatically builds and sends Sales Invoice and Credit Notes payloads

- Integrates with /SalesInformation/SaveSales for sales save

- Integrates with /SalesInformation/SaveCreditNote for Return sales save


---

### 6. Stock Adjustment
Handles real-time stock synchronization with ZRA when:

Goods are sold.

#### Key Capabilities:

Posts updated stock quantities to Smart Invoice system

Supports /StockItemInformation/saveStockItems



### Background Jobs & Integration Requests 

Item registration runs **asynchronously**:  

```python
enqueue(
    method=_process_item_registration,
    queue="long",
    job_name=f"Register Item {item.name} with Smart Zambia",
    timeout=300,
    item_name=item.name,
    settings_name=settings["name"],
)
```
- Jobs are visible under Background Jobs Desk

- Each request is tracked in Integration Requests

---
 **Developer Notes**

### Error Handling  
- Done via an `ErrorObserver`  
- Errors are logged instead of failing silently  

### Key Modules  
- `utils/payload_utils.py` → builds request payloads  
- `apis/api_processor.py` → orchestrates API requests  
- `apis/api_builder.py` → executes remote calls  
- `item_api.py` → item registration workflows  

### Custom Fields  
Use Frappe Export Customizations to export/import custom fields into your ERPNext instance:  

```bash
bench migrate
```
---


**Roadmap**
- Stock Master Information
- Automatic scheduled sync of codes, and Hooks overrides
- Unit tests for payload builders and API calls

---

##  Integrated Endpoints

| #  | Endpoint Name              | ERPNext DocType                        | Purpose                                         |
|----|-----------------------------|----------------------------------------|-------------------------------------------------|
| 1  | `/InitializationInfo/selectInitInfo`          | Crystal ZRA Smart Invoice Settings      | Links ERPNext device with Smart Zambia VSDC     |
| 2  | `/CodeData/selectCodes`          | Smart Standard Codes (custom doctypes) | Retrieves classification, unit, and tax codes   |
| 3  | `/ItemsClassInformation/selectItemsClass`     | Smart Item Classification Codes        | Fetches valid item classification codes (itemClsCd) |
| 4  | `/ItemInformation/saveItem` (Item Management)| Item                                   | Registers ERPNext items in Smart Zambia system  |
| 5  | `/SalesInformation/SaveSales` (Sales Management)| Normal Sales Invoice                                   | Accepts invoice information, customized to a particular invoicing system and submits it to ZRA
  |
| 6  | `/SalesInformation/SaveCreditNote` (Sales Management)| Credit Note                                   | Accepts credit invoice information and submits it to ZRA  |
| 7  | `/SalesInformation/SelectInvoice` (Sales Management)| Sales Invoice                                   | Takes a SelectInvoice query and returns the invoice that exists in the ZRA environment  |
| 8  | `/StockItemInformation/SaveStockItems` ()| Stock Item Information                                   | Add stock items that have been recorded from approved sales to Smart Invoice.  |
| 9  | `/Users/GetToken` (User)|                                    | Logs in a user to auth system using the username and password  |
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
