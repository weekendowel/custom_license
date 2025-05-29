import frappe
import requests
from frappe.utils.pdf import get_pdf
from frappe.utils.file_manager import save_file

@frappe.whitelist()
def send_sales_order_confirmation(sales_order_name):
    sales_order = frappe.get_doc("Sales Order", sales_order_name)

    # Get the customer's primary contact email
    contact_email = None
    if sales_order.contact_person:
        contact_doc = frappe.get_doc("Contact", sales_order.contact_person)
        for email in contact_doc.email_ids:
            if email.is_primary:
                contact_email = email.email_id
                break

    if not contact_email:
        frappe.throw("No contact email found for the customer linked to this Sales Order.")

    license_info_rows = ""

    for item in sales_order.items:
        try:
            quantity = int(item.qty)

            for i in range(quantity):
                api_url = f"http://192.168.2.2:9002/createnew?partcode={item.item_code}&purchaseorder={sales_order.name}"
                frappe.logger().info(f"Fetching license for item {item.item_code} (license {i+1} of {quantity}) from {api_url}")
                response = requests.post(api_url, timeout=10)
                response.raise_for_status()

                response_data = response.json()
                license_key = response_data.get('LicenseKey', 'NO_LICENSE_RECEIVED')
                serial_number = response_data.get('SerialNumber', 'NO_SERIAL_NUMBER')

                license_info_rows += f"""
                <tr>
                    <td>{item.item_code}</td>
                    <td>{item.description}</td>
                    <td>1</td>
                    <td>{serial_number}</td>
                </tr>
                <tr>
                    <td></td>
                    <td>Online activation</td>
                    <td colspan="2"><strong>{license_key}</strong></td>
                </tr>
                """

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), f"License generation failed for {item.item_code}")

    if not license_info_rows:
        frappe.throw("No license documents could be generated.")

    # Build the HTML content with improved layout
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>License Keys from ArrivalNet</title>
        <style>
            @page {{
                margin: 25mm;
            }}
            body {{
                font-family: Arial, sans-serif;
                font-size: 12px;
                color: #333;
                padding: 20px;
                background-color: #fff;
            }}
            .email-container {{
                max-width: 700px;
                margin: auto;
            }}
            .header {{
                text-align: center;
                margin-bottom: 20px;
            }}
            .header img {{
                max-height: 60px;
            }}
            h2 {{
                color: #005288;
                margin-top: 10px;
            }}
            p {{
                margin: 8px 0;
                line-height: 1.5;
            }}
            table.license-table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
            }}
            table.license-table th,
            table.license-table td {{
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
                vertical-align: top;
                word-break: break-word;
            }}
            table.license-table th {{
                background-color: #f2f2f2;
            }}
            strong {{
                font-weight: bold;
            }}
            a {{
                color: #005288;
                text-decoration: none;
            }}
        </style>
    </head>
    <body>
        <div class="email-container">
            <div class="header">
                <img src="https://www.arrivalnet.se/site/wp-content/uploads/2020/03/Arrivalnet-logo-large-with-text-480x125.png" alt="ArrivalNet Logo" />

            </div>

            <p><strong>Thank you for your purchase!</strong></p>
            <p><strong>Customer Purchase Order:</strong> {sales_order.po_no or 'N/A'}</p>
            <p><strong>Sales Order Number:</strong> {sales_order.name}</p>
            <p><strong>Order Date:</strong> {sales_order.transaction_date.strftime('%Y-%m-%d')}</p>
            <p>Here are your license keys:</p>

            <table class="license-table">
                <colgroup>
                    <col style="width: 20%;">
                    <col style="width: 35%;">
                    <col style="width: 15%;">
                    <col style="width: 30%;">
                </colgroup>
                <tr>
                    <th>Part number</th>
                    <th>Description</th>
                    <th>Amount</th>
                    <th>Serial number</th>
                </tr>
                {license_info_rows}
            </table>

            <p>To activate your license, enter the code above in the software’s key field and click <strong>“Online Activation.”</strong></p>
            <p>If you're offline, please send this document and your hardware ID to <a href="mailto:order@arrivalnet.se">order@arrivalnet.se</a>.</p>
            <p>You can download the software and manuals here: <a href="http://www.arrivalnet.se/site/downloads/">www.arrivalnet.se/site/downloads/</a></p>

            <p>Best regards,<br><strong>ArrivalNet</strong></p>
        </div>
    </body>
    </html>
    """

    # Generate PDF from HTML
    pdf_file = get_pdf(html_content)
    filename = f"License_Confirmation_{sales_order.name}.pdf"

    # Attach file to Sales Order
    save_file(filename, pdf_file, "Sales Order", sales_order.name, is_private=0)

    # Send email with PDF attachment and BCC
    frappe.sendmail(
        recipients=[contact_email],
        subject=f"Your License Keys from ArrivalNet on order {sales_order.po_no or sales_order.name}",
        message=html_content,
        delayed=False,
        bcc=["order@arrivalnet.se"],
        attachments=[{
            "fname": filename,
            "fcontent": pdf_file
        }]
    )
