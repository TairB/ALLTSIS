-- =============================================================================
-- procedures.sql
-- TSIS1 — New Stored Procedures & Functions
-- (Practice 8 procedures are NOT repeated here)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- PROCEDURE: add_phone
-- Adds a phone number (with type) to an existing contact by first_name.
-- Usage: CALL add_phone('Ali', '+77011112233', 'mobile');
-- -----------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE add_phone(
    p_contact_name VARCHAR,
    p_phone        VARCHAR,
    p_type         VARCHAR DEFAULT 'mobile'
)
LANGUAGE plpgsql AS $$
DECLARE
    v_contact_id INT;
BEGIN
    -- Find contact
    SELECT id INTO v_contact_id
    FROM phonebook
    WHERE first_name ILIKE p_contact_name
    LIMIT 1;

    IF v_contact_id IS NULL THEN
        RAISE EXCEPTION 'Contact "%" not found.', p_contact_name;
    END IF;

    -- Validate phone type
    IF p_type NOT IN ('home', 'work', 'mobile') THEN
        RAISE EXCEPTION 'Invalid phone type "%". Use: home, work, mobile.', p_type;
    END IF;

    -- Insert phone (ignore if already exists)
    INSERT INTO phones (contact_id, phone, type)
    VALUES (v_contact_id, p_phone, p_type)
    ON CONFLICT (contact_id, phone) DO NOTHING;

    RAISE NOTICE 'Phone % (%) added to contact %.', p_phone, p_type, p_contact_name;
END;
$$;


-- -----------------------------------------------------------------------------
-- PROCEDURE: move_to_group
-- Moves a contact to a group; creates the group if it does not exist.
-- Usage: CALL move_to_group('Ali', 'VIP');
-- -----------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE move_to_group(
    p_contact_name VARCHAR,
    p_group_name   VARCHAR
)
LANGUAGE plpgsql AS $$
DECLARE
    v_contact_id INT;
    v_group_id   INT;
BEGIN
    -- Find contact
    SELECT id INTO v_contact_id
    FROM phonebook
    WHERE first_name ILIKE p_contact_name
    LIMIT 1;

    IF v_contact_id IS NULL THEN
        RAISE EXCEPTION 'Contact "%" not found.', p_contact_name;
    END IF;

    -- Find or create group
    SELECT id INTO v_group_id FROM groups WHERE name ILIKE p_group_name LIMIT 1;

    IF v_group_id IS NULL THEN
        INSERT INTO groups (name) VALUES (p_group_name)
        RETURNING id INTO v_group_id;
        RAISE NOTICE 'Created new group: %', p_group_name;
    END IF;

    -- Move contact
    UPDATE phonebook SET group_id = v_group_id WHERE id = v_contact_id;

    RAISE NOTICE 'Contact "%" moved to group "%".', p_contact_name, p_group_name;
END;
$$;


-- -----------------------------------------------------------------------------
-- FUNCTION: search_contacts
-- Extended pattern search: matches first_name, last_name, email, AND
-- all phone numbers in the phones table.
-- Usage: SELECT * FROM search_contacts('gmail');
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION search_contacts(p_query TEXT)
RETURNS TABLE(
    id         INT,
    first_name VARCHAR,
    last_name  VARCHAR,
    email      VARCHAR,
    birthday   DATE,
    grp        VARCHAR,
    phones_list TEXT
)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
        SELECT
            pb.id,
            pb.first_name,
            pb.last_name,
            pb.email,
            pb.birthday,
            g.name                                   AS grp,
            STRING_AGG(ph.phone || ' (' || ph.type || ')', ', '
                       ORDER BY ph.type)             AS phones_list
        FROM phonebook pb
        LEFT JOIN groups g  ON g.id  = pb.group_id
        LEFT JOIN phones ph ON ph.contact_id = pb.id
        WHERE pb.first_name ILIKE '%' || p_query || '%'
           OR pb.last_name  ILIKE '%' || p_query || '%'
           OR pb.email      ILIKE '%' || p_query || '%'
           OR ph.phone      ILIKE '%' || p_query || '%'
        GROUP BY pb.id, pb.first_name, pb.last_name,
                 pb.email, pb.birthday, g.name
        ORDER BY pb.first_name;
END;
$$;
