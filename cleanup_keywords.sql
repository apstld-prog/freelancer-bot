-- cleanup_keywords.sql
-- Καθαρίζει τη βάση από άκυρα user_id και κρατά μόνο το δικό σου (5254014824)

DELETE FROM keyword WHERE user_id NOT IN (5254014824);

-- Προαιρετικά, αν θέλεις να είσαι βέβαιος ότι έχουν καθαριστεί όλα:
VACUUM;

-- Εμφανίζει τις εγγραφές που έμειναν
SELECT user_id, keyword FROM keyword;
