import { APP_CONFIG } from '@/config/app.config';

const API_URL = APP_CONFIG.apiUrl;
export const API_ENDPOINTS = {
    API_URL,
    // Auth
    LOGIN: `${API_URL}/auth/login`,
    REGISTER: `${API_URL}/auth/register`,
    CURRENT_USER: `${API_URL}/auth/me`,
    // Products
    CREATE_PRODUCT: `${API_URL}/products`,
    GET_PRODUCTS: `${API_URL}/products`,
    GET_PRODUCT_BY_ID: `${API_URL}/products/{id}`,
    UPDATE_PRODUCT: `${API_URL}/products/{id}`,
    DELETE_PRODUCT: `${API_URL}/products/{id}`,

    // Orders:
    GET_ORDERS: `${API_URL}/orders/my-orders`,
    GET_ORDER_BY_ID: `${API_URL}/orders/{id}`,
    CREATE_GUEST_ORDER: `${API_URL}/orders/guest`,
    CREATE_ORDER: `${API_URL}/orders`,
    DELETE_ORDER: `${API_URL}/orders/{id}`,
    UPDATE_ORDER_STATUS: `${API_URL}/orders/{id}/status`,
    
    // Variants
    GET_VARIANTS: `${API_URL}/variants/product/{id}`,
    GET_VARIANT_BY_ID: `${API_URL}/variants/{id}`,
    UPDATE_VARIANT: `${API_URL}/variants/{id}`,
    CREATE_VARIANT: `${API_URL}/variants`,
    DELETE_VARIANT: `${API_URL}/variants/{id}`,
   
    // CART
    GET_CART: `${API_URL}/cart`,
    ADD_TO_CART: `${API_URL}/cart`,
    UPDATE_CART_ITEM_QUANTITY: `${API_URL}/cart/{id}`,
    DELETE_CART_ITEM: `${API_URL}/cart/{id}`,

    // SALES REPORT:
    GET_SALES_REPORT: `${API_URL}/admin/sales-report`,
    GET_DASHBOARD_STATS: `${API_URL}/admin/dashboard`,
    GET_ALL_USERS: `${API_URL}/admin/all-users`,
    GET_USER_BY_ID: `${API_URL}/admin/user/{id}`,
}