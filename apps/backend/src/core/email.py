from .config import settings
from typing import Optional
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class EmailService:

    @staticmethod
    def _send_smtp_email(to_email: str, subject: str, html_content: str) -> bool:
        try:
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = settings.FROM_EMAIL
            message["To"] = to_email

            html_part = MIMEText(html_content, "html")
            message.attach(html_part)

            use_tls = str(settings.SMTP_TLS).lower() == "true"

            if use_tls:
                context = ssl.create_default_context()
                with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                    server.starttls(context=context)
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                    server.sendmail(settings.FROM_EMAIL, to_email, message.as_string())
            else:
                with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                    server.sendmail(settings.FROM_EMAIL, to_email, message.as_string())

            return True

        except Exception as e:
            print(f"SMTP Error: {str(e)}")
            return False

    @staticmethod
    def send_order_confirmation(
        to_email: str,
        customer_name: str,
        order_id: int,
        total_amount: float,
        order_items: list
    ) -> bool:
        """Send order confirmation email to customer"""
        try:
            # Build order items HTML
            items_html = ""
            for item in order_items:
                items_html += f"""
                <tr>
                    <td style="padding: 10px; border-bottom: 1px solid #eee;">
                        {item['product_name']} - {item['color']}/{item['size']}
                    </td>
                    <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: center;">
                        {item['quantity']}
                    </td>
                    <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: right;">
                        Rs. {item['price']:,.2f}
                    </td>
                </tr>
                """
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>Order Confirmation</title>
            </head>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #4CAF50;">Order Confirmation</h2>
                    
                    <p>Dear {customer_name},</p>
                    
                    <p>Thank you for your order! Your order has been received and is being processed.</p>
                    
                    <div style="background-color: #f9f9f9; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">Order Details</h3>
                        <p><strong>Order ID:</strong> #{order_id}</p>
                        <p><strong>Total Amount:</strong> Rs. {total_amount:,.2f}</p>
                    </div>
                    
                    <h3>Order Items</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <thead>
                            <tr style="background-color: #f2f2f2;">
                                <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Item</th>
                                <th style="padding: 10px; text-align: center; border-bottom: 2px solid #ddd;">Quantity</th>
                                <th style="padding: 10px; text-align: right; border-bottom: 2px solid #ddd;">Price</th>
                            </tr>
                        </thead>
                        <tbody>
                            {items_html}
                        </tbody>
                        <tfoot>
                            <tr>
                                <td colspan="2" style="padding: 15px; text-align: right; font-weight: bold;">Total:</td>
                                <td style="padding: 15px; text-align: right; font-weight: bold;">Rs. {total_amount:,.2f}</td>
                            </tr>
                        </tfoot>
                    </table>
                    
                    <p style="margin-top: 30px;">We'll send you another email when your order ships.</p>
                    
                    <p>For any questions, please contact us:</p>
                    <p>
                        WhatsApp: {settings.SUPPORT_WHATSAPP}<br>
                        Email: {settings.SUPPORT_EMAIL}
                    </p>
                    
                    <p style="color: #666; font-size: 12px; margin-top: 30px;">
                        This is an automated email. Please do not reply to this message.
                    </p>
                </div>
            </body>
            </html>
            """
            

            subject = f"Order Confirmation - Order #{order_id}"
            return EmailService._send_smtp_email(to_email, subject, html_content)
            
        except Exception as e:
            print(f"Error sending email: {str(e)}")
            return False
    
    @staticmethod
    def send_admin_notification(
        order_id: int,
        customer_name: str,
        customer_email: str,
        customer_whatsapp: str,
        total_amount: float,
        location: str
    ) -> bool:
        """Send new order notification to admin"""
        try:
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>New Order Received</title>
            </head>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #FF5722;">New Order Received!</h2>
                    
                    <div style="background-color: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #ffc107;">
                        <h3 style="margin-top: 0;">Order #{order_id}</h3>
                        <p><strong>Total Amount:</strong> Rs. {total_amount:,.2f}</p>
                    </div>
                    
                    <h3>Customer Information</h3>
                    <ul>
                        <li><strong>Name:</strong> {customer_name}</li>
                        <li><strong>Email:</strong> {customer_email}</li>
                        <li><strong>WhatsApp:</strong> {customer_whatsapp}</li>
                        <li><strong>Location:</strong> {location}</li>
                    </ul>
                    
                    <p style="margin-top: 30px;">
                        Please login to the admin dashboard to view full order details and process the order.
                    </p>
                </div>
            </body>
            </html>
            """
            

            subject = f"New Order #{order_id} - Rs. {total_amount:,.2f}"
            admin_email = settings.SUPPORT_EMAIL

            return EmailService._send_smtp_email(admin_email, subject, html_content)
            
        except Exception as e:
            print(f"Error sending admin notification: {str(e)}")
            return False
    
    @staticmethod
    def send_status_update(
        to_email: str,
        customer_name: str,
        order_id: int,
        new_status: str
    ) -> bool:
        """Send order status update email"""
        try:
            status_messages = {
                "confirmed": "Your order has been confirmed and is being prepared for shipment.",
                "shipped": "Great news! Your order has been shipped and is on its way to you.",
                "delivered": "Your order has been delivered. We hope you love your purchase!"
            }
            
            message = status_messages.get(new_status, "Your order status has been updated.")
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>Order Status Update</title>
            </head>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #2196F3;">Order Status Update</h2>
                    
                    <p>Dear {customer_name},</p>
                    
                    <p>{message}</p>
                    
                    <div style="background-color: #e3f2fd; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <p style="margin: 0;"><strong>Order ID:</strong> #{order_id}</p>
                        <p style="margin: 10px 0 0 0;"><strong>Status:</strong> <span style="text-transform: capitalize;">{new_status}</span></p>
                    </div>
                    
                    <p>For any questions, please contact us:</p>
                    <p>
                        WhatsApp: {settings.SUPPORT_WHATSAPP}<br>
                        Email: {settings.SUPPORT_EMAIL}
                    </p>
                </div>
            </body>
            </html>
            """
            
            subject = f"Order #{order_id} - Status Updated"
            return EmailService._send_smtp_email(to_email, subject, html_content)
            
        except Exception as e:
            print(f"Error sending status update email: {str(e)}")
            return False
    
    @staticmethod
    def send_order_deletion_notification(
        order_id: int,
        customer_name: str,
        customer_email: str,
        customer_whatsapp: str,
        total_amount: float,
        location: str,
        order_status: str,
        order_items: list
    ) -> bool:
        """Send order deletion notification to admin"""
        try:
            # Build order items HTML
            items_html = ""
            for item in order_items:
                items_html += f"""
                <tr>
                    <td style="padding: 10px; border-bottom: 1px solid #eee;">
                        {item['product_name']} - {item['color']}/{item['size']}
                    </td>
                    <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: center;">
                        {item['quantity']}
                    </td>
                    <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: right;">
                        Rs. {item['price']:,.2f}
                    </td>
                </tr>
                """
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>Order Deleted</title>
            </head>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #F44336;">⚠️ Order Deleted</h2>
                    
                    <div style="background-color: #ffebee; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #f44336;">
                        <h3 style="margin-top: 0; color: #c62828;">Order #{order_id} has been deleted</h3>
                        <p><strong>Total Amount:</strong> Rs. {total_amount:,.2f}</p>
                        <p><strong>Status at deletion:</strong> <span style="text-transform: capitalize;">{order_status}</span></p>
                    </div>
                    
                    <h3>Customer Information</h3>
                    <ul>
                        <li><strong>Name:</strong> {customer_name}</li>
                        <li><strong>Email:</strong> {customer_email}</li>
                        <li><strong>WhatsApp:</strong> {customer_whatsapp}</li>
                        <li><strong>Location:</strong> {location}</li>
                    </ul>
                    
                    <h3>Order Items (Stock Restored)</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <thead>
                            <tr style="background-color: #f2f2f2;">
                                <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Item</th>
                                <th style="padding: 10px; text-align: center; border-bottom: 2px solid #ddd;">Quantity</th>
                                <th style="padding: 10px; text-align: right; border-bottom: 2px solid #ddd;">Price</th>
                            </tr>
                        </thead>
                        <tbody>
                            {items_html}
                        </tbody>
                        <tfoot>
                            <tr>
                                <td colspan="2" style="padding: 15px; text-align: right; font-weight: bold;">Total:</td>
                                <td style="padding: 15px; text-align: right; font-weight: bold;">Rs. {total_amount:,.2f}</td>
                            </tr>
                        </tfoot>
                    </table>
                    
                    <p style="margin-top: 30px; color: #666; font-size: 14px;">
                        <strong>Note:</strong> Stock quantities have been automatically restored for all items in this order.
                    </p>
                </div>
            </body>
            </html>
            """
            
            subject = f"Order #{order_id} Deleted - Rs. {total_amount:,.2f}"
            admin_email = settings.SUPPORT_EMAIL
            
            return EmailService._send_smtp_email(admin_email, subject, html_content)
            
        except Exception as e:
            print(f"Error sending order deletion notification: {str(e)}")
            return False