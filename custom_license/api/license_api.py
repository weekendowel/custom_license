import frappe
import requests

@frappe.whitelist()
def send_sales_order_confirmation(sales_order_name):
    sales_order = frappe.get_doc("Sales Order", sales_order_name)

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
                api_url = f"https://www.arrivalnet.se/php_scripts/get_new_license.php?item_code={item.item_code}&customer={contact_email}"
                frappe.logger().info(f"Fetching license for item {item.item_code} (license {i+1} of {quantity}) from {api_url}")
                response = requests.get(api_url, timeout=10)
                response.raise_for_status()

                license_key = response.json().get('license_key', 'NO_LICENSE_RECEIVED')

                license_info_rows += f"""
                <tr>
                    <td>{item.item_code}</td>
                    <td>{item.item_name}</td>
                    <td>1</td>
                    <td>{sales_order.name}</td>
                </tr>
                <tr>
                    <td></td>
                    <td>Online activation</td>
                    <td colspan="2"><strong>{license_key}</strong></td>
                </tr>
                """

        except Exception as e:
            frappe.log_error(f"License generation failed for {item.item_code}: {str(e)}")

    if license_info_rows:
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>License Keys from ArrivalNet</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background-color: #f9f9f9;
                    color: #333;
                }}
                .email-container {{
                    background-color: #ffffff;
                    max-width: 700px;
                    margin: auto;
                    padding: 30px;
                    border-radius: 8px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.05);
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 30px;
                }}
                .header img {{
                    max-height: 60px;
                    margin-bottom: 10px;
                }}
                h2 {{
                    color: #005288;
                    font-size: 20px;
                }}
                p {{
                    font-size: 15px;
                    line-height: 1.6;
                }}
                table.license-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 20px;
                }}
                table.license-table th, table.license-table td {{
                    border: 1px solid #ccc;
                    padding: 10px;
                    font-size: 14px;
                }}
                table.license-table th {{
                    background-color: #f2f2f2;
                    text-align: left;
                }}
                a {{
                    color: #005288;
                }}
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <img src="https://www.arrivalnet.se/site/wp-content/uploads/2020/03/Arrivalnet-logo-large-with-text-480x125.png" alt="ArrivalNet Logo" />
                    <h2>{sales_order.customer_name}</h2>
                </div>

            <p><strong>Thank you for your purchase!</strong></p>
                <p><strong>Customer Purchase Order:</strong> {sales_order.po_no or 'N/A'}</p>
                <p><strong>Sales Order Number:</strong> {sales_order.name}</p>
                <p><strong>Order Date:</strong> {sales_order.transaction_date.strftime('%Y-%m-%d')}</p>
                <p>Here is your order confirmation and license keys:</p>


                <table class="license-table">
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

        frappe.sendmail(
            recipients=[contact_email],
            subject="Your License Keys from ArrivalNet",
            message=html_content,
            delayed=False
        )
    else:
        frappe.throw("No license documents could be generated.")

