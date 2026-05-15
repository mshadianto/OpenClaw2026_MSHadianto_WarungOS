-- WarungOS Demo Database Schema
-- Designed to support 3 agents: Inventory Sentinel, Procurement Negotiator, Customer Concierge

DROP TABLE IF EXISTS inventory;
DROP TABLE IF EXISTS sales_history;
DROP TABLE IF EXISTS suppliers;
DROP TABLE IF EXISTS supplier_offerings;
DROP TABLE IF EXISTS customer_waitlist;
DROP TABLE IF EXISTS purchase_orders;
DROP TABLE IF EXISTS agent_activity_log;

-- Current inventory snapshot
CREATE TABLE inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT NOT NULL,
    current_stock INTEGER NOT NULL,
    unit TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Historical sales (for depletion forecasting)
CREATE TABLE sales_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT NOT NULL,
    quantity_sold INTEGER NOT NULL,
    sale_date DATE NOT NULL
);

-- Supplier directory
CREATE TABLE suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    contact TEXT,
    rating REAL,  -- 1.0 to 5.0
    avg_eta_hours INTEGER,
    moq_friendly BOOLEAN
);

-- What each supplier sells & their pricing
CREATE TABLE supplier_offerings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id INTEGER REFERENCES suppliers(id),
    item_name TEXT NOT NULL,
    unit_price INTEGER NOT NULL,  -- in IDR
    moq INTEGER NOT NULL,  -- minimum order quantity
    in_stock BOOLEAN DEFAULT 1
);

-- Customers waiting for restock
CREATE TABLE customer_waitlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name TEXT NOT NULL,
    phone TEXT,
    item_requested TEXT NOT NULL,
    quantity INTEGER DEFAULT 1,
    notes TEXT,
    notified BOOLEAN DEFAULT 0
);

-- Purchase orders (created by Procurement Negotiator)
CREATE TABLE purchase_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    po_number TEXT UNIQUE NOT NULL,
    supplier_id INTEGER REFERENCES suppliers(id),
    items_json TEXT NOT NULL,
    total_amount INTEGER NOT NULL,
    doku_va_number TEXT,
    status TEXT DEFAULT 'PENDING',  -- PENDING, PAID, REJECTED, DELIVERED
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Agent activity audit log (for transparency in demo)
CREATE TABLE agent_activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============ SEED DATA ============

-- Realistic inventory snapshot (Warung Bu Sari, Jakarta)
INSERT INTO inventory (item_name, current_stock, unit) VALUES
    ('Ayam Fillet', 5, 'kg'),
    ('Cabai Merah', 2, 'kg'),
    ('Bawang Merah', 8, 'kg'),
    ('Telur Ayam', 30, 'butir'),
    ('Minyak Goreng', 12, 'liter'),
    ('Beras Premium', 25, 'kg'),
    ('Tepung Terigu', 7, 'kg'),
    ('Gula Pasir', 15, 'kg');

-- Sales history (last 7 days, realistic daily consumption)
INSERT INTO sales_history (item_name, quantity_sold, sale_date) VALUES
    ('Ayam Fillet', 3, date('now', '-1 day')),
    ('Ayam Fillet', 4, date('now', '-2 day')),
    ('Ayam Fillet', 2, date('now', '-3 day')),
    ('Ayam Fillet', 3, date('now', '-4 day')),
    ('Cabai Merah', 1, date('now', '-1 day')),
    ('Cabai Merah', 2, date('now', '-2 day')),
    ('Cabai Merah', 1, date('now', '-3 day')),
    ('Bawang Merah', 2, date('now', '-1 day')),
    ('Bawang Merah', 3, date('now', '-2 day')),
    ('Telur Ayam', 12, date('now', '-1 day')),
    ('Telur Ayam', 15, date('now', '-2 day'));

-- 3 suppliers with different trade-offs
INSERT INTO suppliers (name, contact, rating, avg_eta_hours, moq_friendly) VALUES
    ('PT Sumber Ayam Jaya', '081234567001', 4.8, 18, 1),   -- High quality, fast, MOQ-friendly
    ('CV Mitra Pangan Cepat', '081234567002', 4.2, 12, 1),  -- Cheapest, fastest, lower rating
    ('UD Pasar Tradisional', '081234567003', 4.5, 36, 0);   -- Mid-tier, slow, strict MOQ

-- Supplier offerings (each supplier has different pricing/MOQ)
INSERT INTO supplier_offerings (supplier_id, item_name, unit_price, moq) VALUES
    -- PT Sumber Ayam Jaya
    (1, 'Ayam Fillet', 65000, 5),
    (1, 'Cabai Merah', 45000, 2),
    (1, 'Bawang Merah', 32000, 5),
    -- CV Mitra Pangan Cepat (cheaper but lower rating)
    (2, 'Ayam Fillet', 58000, 10),
    (2, 'Cabai Merah', 42000, 3),
    (2, 'Bawang Merah', 30000, 10),
    -- UD Pasar Tradisional (mid, strict MOQ)
    (3, 'Ayam Fillet', 62000, 15),
    (3, 'Cabai Merah', 44000, 5),
    (3, 'Bawang Merah', 31000, 10);

-- Customer waitlist
INSERT INTO customer_waitlist (customer_name, phone, item_requested, quantity, notes) VALUES
    ('Bu Sari', '081234001', 'Ayam Fillet', 2, 'Untuk catering hari Kamis'),
    ('Pak Budi', '081234002', 'Ayam Fillet', 1, 'Langganan setiap Jumat'),
    ('Mbak Ratna', '081234003', 'Ayam Fillet', 3, 'Buat rumah makan'),
    ('Bu Lina', '081234004', 'Cabai Merah', 1, 'Stok bumbu warung');
