import frappe
import requests
from decimal import Decimal, InvalidOperation
from html import escape
from frappe.utils.pdf import get_pdf
from frappe.utils.file_manager import save_file


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

    license_info_rows = []
    generation_errors = []

    for item in sales_order.items:
        try:
            quantity_decimal = Decimal(str(item.qty))
            if quantity_decimal <= 0 or quantity_decimal != quantity_decimal.to_integral_value():
                raise ValueError(f"License quantity must be a positive whole number (got {item.qty}).")
            quantity = int(quantity_decimal)

            # A stable row-specific reference makes retries idempotent while allowing
            # two separate license rows in the same Sales Order to get separate keys.
            purchase_order_reference = f"{sales_order.name}_{item.name}"
            api_url = "http://192.168.2.2:9002/createnew"
            params = {
                "partCode": item.item_code,
                "purchaseOrder": purchase_order_reference,
                "amount": quantity,
            }
            frappe.logger().info(
                f"Requesting one license for item {item.item_code}, quantity {quantity}, "
                f"order row {item.name}."
            )
            response = requests.post(api_url, params=params, timeout=15)
            response.raise_for_status()

            response_data = response.json()
            license_key = response_data.get("LicenseKey")
            serial_number = response_data.get("SerialNumber")
            issued_amount = int(response_data.get("Amount", 0))

            if not license_key:
                raise ValueError("The license service returned no license key.")
            if issued_amount != quantity:
                raise ValueError(
                    f"The license service returned Amount={issued_amount}, but the Sales Order row has quantity {quantity}."
                )

            license_info_rows.append(f"""
                <tr>
                    <td>{escape(str(item.item_code or ""))}</td>
                    <td>{escape(str(item.description or ""))}</td>
                    <td>{quantity}</td>
                    <td>{escape(str(serial_number or "NO_SERIAL_NUMBER"))}</td>
                </tr>
                <tr>
                    <td></td>
                    <td>Online activation</td>
                    <td colspan="2"><strong>{escape(str(license_key))}</strong></td>
                </tr>
            """)

        except Exception as exc:
            frappe.log_error(frappe.get_traceback(), f"License generation failed for {item.item_code}")
            generation_errors.append(f"{item.item_code} (order row {item.name}): {exc}")

    # Do not email a partial confirmation. Successfully generated keys use the
    # stable row reference above, so retrying this function will retrieve those keys.
    if generation_errors:
        frappe.throw("License generation failed:\n" + "\n".join(generation_errors))

    if not license_info_rows:
        frappe.throw("No license documents could be generated.")

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>License Keys from ArrivalNet</title>
        <style>
            @page {{ margin: 25mm; }}
            body {{ font-family: Arial, sans-serif; font-size: 12px; color: #333; padding: 20px; background-color: #fff; }}
            .email-container {{ max-width: 700px; margin: auto; }}
            .header {{ text-align: center; margin-bottom: 20px; }}
            .header img {{ max-height: 60px; }}
            h2 {{ color: #005288; margin-top: 10px; }}
            p {{ margin: 8px 0; line-height: 1.5; }}
            table.license-table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            table.license-table th, table.license-table td {{ border: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; word-break: break-word; }}
            table.license-table th {{ background-color: #f2f2f2; }}
            strong {{ font-weight: bold; }}
            a {{ color: #005288; text-decoration: none; }}
        </style>
    </head>
    <body>
        <div class="email-container">
            <div class="header">
                <img src="https://www.arrivalnet.se/site/wp-content/uploads/2020/03/Arrivalnet-logo-large-with-text-480x125.png" alt="ArrivalNet Logo" />
            </div>
            <p><strong>Thank you for your purchase!</strong></p>
            <p><strong>Customer Purchase Order:</strong> {escape(str(sales_order.po_no or 'N/A'))}</p>
            <p><strong>Sales Order Number:</strong> {escape(str(sales_order.name))}</p>
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
                {''.join(license_info_rows)}
            </table>
            <p>To activate your license, enter the code above in the software’s key field and click <strong>“Online Activation.”</strong></p>
            <p>If you're offline, please send this document and your hardware ID to <a href="mailto:order@arrivalnet.se">order@arrivalnet.se</a>.</p>
            <p>You can download the software and manuals here: <a href="http://www.arrivalnet.se/site/downloads/">www.arrivalnet.se/site/downloads/</a></p>
            <p>Best regards,<br><strong>ArrivalNet</strong></p>
        </div>
    </body>
    </html>
    """

    pdf_file = get_pdf(html_content)
    filename = f"License_Confirmation_{sales_order.name}.pdf"
    save_file(filename, pdf_file, "Sales Order", sales_order.name, is_private=0)

    frappe.sendmail(
        recipients=[contact_email],
        subject=f"Your License Keys from ArrivalNet on order {sales_order.po_no or sales_order.name}",
        message=html_content,
        delayed=False,
        bcc=["order@arrivalnet.se"],
        attachments=[{"fname": filename, "fcontent": pdf_file}],
    )
