package storage

import (
	"context"
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"strings"
	"sync"
	"time"

	_ "github.com/lib/pq"
	"golang.org/x/crypto/pbkdf2"
)

// PostgresStorage implements Storage using PostgreSQL
type PostgresStorage struct {
	db         *sql.DB
	password   []byte
	mu         sync.RWMutex
	shareCache map[string]*ShareData
}

// NewPostgresStorage creates a new PostgreSQL-based storage
func NewPostgresStorage(databaseURL string, password string) (*PostgresStorage, error) {
	// Add sslmode=disable for Railway internal connections if not specified
	if !strings.Contains(databaseURL, "sslmode=") {
		if strings.Contains(databaseURL, "?") {
			databaseURL += "&sslmode=disable"
		} else {
			databaseURL += "?sslmode=disable"
		}
	}

	db, err := sql.Open("postgres", databaseURL)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to database: %w", err)
	}

	// Test connection
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	// Create table if not exists
	_, err = db.ExecContext(ctx, `
		CREATE TABLE IF NOT EXISTS mpc_bank_shares (
			keyset_id VARCHAR(64) PRIMARY KEY,
			encrypted_data BYTEA NOT NULL,
			created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
			updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
		)
	`)
	if err != nil {
		return nil, fmt.Errorf("failed to create table: %w", err)
	}

	return &PostgresStorage{
		db:         db,
		password:   []byte(password),
		shareCache: make(map[string]*ShareData),
	}, nil
}

// encrypt encrypts share data using AES-256-GCM
func (ps *PostgresStorage) encrypt(share *ShareData) ([]byte, error) {
	// Serialize share data
	plaintext, err := json.Marshal(share)
	if err != nil {
		return nil, fmt.Errorf("failed to serialize share: %w", err)
	}

	// Generate salt
	salt := make([]byte, saltSize)
	if _, err := io.ReadFull(rand.Reader, salt); err != nil {
		return nil, fmt.Errorf("failed to generate salt: %w", err)
	}

	// Derive key using PBKDF2
	key := pbkdf2.Key(ps.password, salt, pbkdf2Iterations, keySize, sha256.New)

	// Create AES-GCM cipher
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, fmt.Errorf("failed to create cipher: %w", err)
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("failed to create GCM: %w", err)
	}

	// Generate nonce
	nonce := make([]byte, nonceSize)
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return nil, fmt.Errorf("failed to generate nonce: %w", err)
	}

	// Encrypt
	ciphertext := gcm.Seal(nil, nonce, plaintext, nil)

	// Create encrypted share
	encrypted := EncryptedShare{
		Salt:       salt,
		Nonce:      nonce,
		Ciphertext: ciphertext,
		CreatedAt:  share.CreatedAt,
	}

	return json.Marshal(encrypted)
}

// decrypt decrypts share data
func (ps *PostgresStorage) decrypt(data []byte) (*ShareData, error) {
	// Parse encrypted share
	var encrypted EncryptedShare
	if err := json.Unmarshal(data, &encrypted); err != nil {
		return nil, fmt.Errorf("failed to parse encrypted share: %w", err)
	}

	// Derive key
	key := pbkdf2.Key(ps.password, encrypted.Salt, pbkdf2Iterations, keySize, sha256.New)

	// Create AES-GCM cipher
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, fmt.Errorf("failed to create cipher: %w", err)
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("failed to create GCM: %w", err)
	}

	// Decrypt
	plaintext, err := gcm.Open(nil, encrypted.Nonce, encrypted.Ciphertext, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to decrypt share: %w", err)
	}

	// Deserialize
	var share ShareData
	if err := json.Unmarshal(plaintext, &share); err != nil {
		return nil, fmt.Errorf("failed to deserialize share: %w", err)
	}

	return &share, nil
}

// SaveShare encrypts and saves a share to PostgreSQL
func (ps *PostgresStorage) SaveShare(share *ShareData) error {
	ps.mu.Lock()
	defer ps.mu.Unlock()

	encryptedData, err := ps.encrypt(share)
	if err != nil {
		return err
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	_, err = ps.db.ExecContext(ctx, `
		INSERT INTO mpc_bank_shares (keyset_id, encrypted_data, created_at, updated_at)
		VALUES ($1, $2, $3, $3)
		ON CONFLICT (keyset_id) DO UPDATE SET
			encrypted_data = EXCLUDED.encrypted_data,
			updated_at = NOW()
	`, share.KeysetID, encryptedData, share.CreatedAt)

	if err != nil {
		return fmt.Errorf("failed to save share to database: %w", err)
	}

	// Update cache
	ps.shareCache[share.KeysetID] = share

	return nil
}

// GetShare loads and decrypts a share from PostgreSQL
func (ps *PostgresStorage) GetShare(keysetID string) (*ShareData, error) {
	ps.mu.RLock()
	if share, ok := ps.shareCache[keysetID]; ok {
		ps.mu.RUnlock()
		return share, nil
	}
	ps.mu.RUnlock()

	ps.mu.Lock()
	defer ps.mu.Unlock()

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	var encryptedData []byte
	err := ps.db.QueryRowContext(ctx,
		"SELECT encrypted_data FROM mpc_bank_shares WHERE keyset_id = $1",
		keysetID,
	).Scan(&encryptedData)

	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("share not found: %s", keysetID)
	}
	if err != nil {
		return nil, fmt.Errorf("failed to query share: %w", err)
	}

	share, err := ps.decrypt(encryptedData)
	if err != nil {
		return nil, err
	}

	// Update cache
	ps.shareCache[keysetID] = share

	return share, nil
}

// DeleteShare removes a share from PostgreSQL
func (ps *PostgresStorage) DeleteShare(keysetID string) error {
	ps.mu.Lock()
	defer ps.mu.Unlock()

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	_, err := ps.db.ExecContext(ctx,
		"DELETE FROM mpc_bank_shares WHERE keyset_id = $1",
		keysetID,
	)
	if err != nil {
		return fmt.Errorf("failed to delete share: %w", err)
	}

	// Remove from cache
	delete(ps.shareCache, keysetID)

	return nil
}

// ListShares returns all keyset IDs
func (ps *PostgresStorage) ListShares() ([]string, error) {
	ps.mu.RLock()
	defer ps.mu.RUnlock()

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	rows, err := ps.db.QueryContext(ctx, "SELECT keyset_id FROM mpc_bank_shares")
	if err != nil {
		return nil, fmt.Errorf("failed to list shares: %w", err)
	}
	defer rows.Close()

	var keysetIDs []string
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return nil, fmt.Errorf("failed to scan keyset_id: %w", err)
		}
		keysetIDs = append(keysetIDs, id)
	}

	return keysetIDs, nil
}

// UpdateShareLastUsed updates the last used timestamp
func (ps *PostgresStorage) UpdateShareLastUsed(keysetID string) error {
	share, err := ps.GetShare(keysetID)
	if err != nil {
		return err
	}

	share.LastUsedAt = time.Now()
	return ps.SaveShare(share)
}

// Close closes the database connection
func (ps *PostgresStorage) Close() error {
	return ps.db.Close()
}
