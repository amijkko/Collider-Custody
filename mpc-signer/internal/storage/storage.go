package storage

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sync"
	"time"

	"golang.org/x/crypto/pbkdf2"
)

const (
	pbkdf2Iterations = 100000
	keySize          = 32 // AES-256
	saltSize         = 32
	nonceSize        = 12 // GCM standard
)

// ShareData represents an MPC key share
type ShareData struct {
	KeysetID        string    `json:"keyset_id"`
	WalletID        string    `json:"wallet_id"`
	PartyIndex      int       `json:"party_index"`
	Threshold       int       `json:"threshold"`
	TotalParties    int       `json:"total_parties"`
	PublicKey       []byte    `json:"public_key"`
	EthereumAddress string    `json:"ethereum_address"`
	ShareBytes      []byte    `json:"share_bytes"` // Encrypted tss-lib LocalPartySaveData
	CreatedAt       time.Time `json:"created_at"`
	LastUsedAt      time.Time `json:"last_used_at"`
}

// EncryptedShare represents the on-disk format
type EncryptedShare struct {
	Salt       []byte    `json:"salt"`
	Nonce      []byte    `json:"nonce"`
	Ciphertext []byte    `json:"ciphertext"`
	CreatedAt  time.Time `json:"created_at"`
}

// Storage interface for share persistence
type Storage interface {
	SaveShare(share *ShareData) error
	GetShare(keysetID string) (*ShareData, error)
	DeleteShare(keysetID string) error
	ListShares() ([]string, error)
	UpdateShareLastUsed(keysetID string) error
}

// FileStorage implements Storage using encrypted files
type FileStorage struct {
	basePath   string
	password   []byte
	mu         sync.RWMutex
	shareCache map[string]*ShareData
}

// NewFileStorage creates a new file-based storage
func NewFileStorage(basePath string, password string) (*FileStorage, error) {
	// Ensure directory exists
	if err := os.MkdirAll(basePath, 0700); err != nil {
		return nil, fmt.Errorf("failed to create storage directory: %w", err)
	}

	return &FileStorage{
		basePath:   basePath,
		password:   []byte(password),
		shareCache: make(map[string]*ShareData),
	}, nil
}

// SaveShare encrypts and saves a share to disk
func (fs *FileStorage) SaveShare(share *ShareData) error {
	fs.mu.Lock()
	defer fs.mu.Unlock()

	// Serialize share data
	plaintext, err := json.Marshal(share)
	if err != nil {
		return fmt.Errorf("failed to serialize share: %w", err)
	}

	// Generate salt
	salt := make([]byte, saltSize)
	if _, err := io.ReadFull(rand.Reader, salt); err != nil {
		return fmt.Errorf("failed to generate salt: %w", err)
	}

	// Derive key using PBKDF2
	key := pbkdf2.Key(fs.password, salt, pbkdf2Iterations, keySize, sha256.New)

	// Create AES-GCM cipher
	block, err := aes.NewCipher(key)
	if err != nil {
		return fmt.Errorf("failed to create cipher: %w", err)
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return fmt.Errorf("failed to create GCM: %w", err)
	}

	// Generate nonce
	nonce := make([]byte, nonceSize)
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return fmt.Errorf("failed to generate nonce: %w", err)
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

	// Serialize to JSON
	encryptedJSON, err := json.Marshal(encrypted)
	if err != nil {
		return fmt.Errorf("failed to serialize encrypted share: %w", err)
	}

	// Write to file
	filename := filepath.Join(fs.basePath, fmt.Sprintf("%s.json", share.KeysetID))
	if err := os.WriteFile(filename, encryptedJSON, 0600); err != nil {
		return fmt.Errorf("failed to write share file: %w", err)
	}

	// Update cache
	fs.shareCache[share.KeysetID] = share

	return nil
}

// GetShare loads and decrypts a share from disk
func (fs *FileStorage) GetShare(keysetID string) (*ShareData, error) {
	fs.mu.RLock()
	if share, ok := fs.shareCache[keysetID]; ok {
		fs.mu.RUnlock()
		return share, nil
	}
	fs.mu.RUnlock()

	fs.mu.Lock()
	defer fs.mu.Unlock()

	// Read from file
	filename := filepath.Join(fs.basePath, fmt.Sprintf("%s.json", keysetID))
	encryptedJSON, err := os.ReadFile(filename)
	if err != nil {
		return nil, fmt.Errorf("failed to read share file: %w", err)
	}

	// Parse encrypted share
	var encrypted EncryptedShare
	if err := json.Unmarshal(encryptedJSON, &encrypted); err != nil {
		return nil, fmt.Errorf("failed to parse encrypted share: %w", err)
	}

	// Derive key
	key := pbkdf2.Key(fs.password, encrypted.Salt, pbkdf2Iterations, keySize, sha256.New)

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

	// Update cache
	fs.shareCache[keysetID] = &share

	return &share, nil
}

// DeleteShare removes a share from disk
func (fs *FileStorage) DeleteShare(keysetID string) error {
	fs.mu.Lock()
	defer fs.mu.Unlock()

	// Delete file
	filename := filepath.Join(fs.basePath, fmt.Sprintf("%s.json", keysetID))
	if err := os.Remove(filename); err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("failed to delete share file: %w", err)
	}

	// Remove from cache
	delete(fs.shareCache, keysetID)

	return nil
}

// ListShares returns all keyset IDs
func (fs *FileStorage) ListShares() ([]string, error) {
	fs.mu.RLock()
	defer fs.mu.RUnlock()

	entries, err := os.ReadDir(fs.basePath)
	if err != nil {
		return nil, fmt.Errorf("failed to read storage directory: %w", err)
	}

	var keysetIDs []string
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		name := entry.Name()
		if filepath.Ext(name) == ".json" {
			keysetIDs = append(keysetIDs, name[:len(name)-5])
		}
	}

	return keysetIDs, nil
}

// UpdateShareLastUsed updates the last used timestamp
func (fs *FileStorage) UpdateShareLastUsed(keysetID string) error {
	share, err := fs.GetShare(keysetID)
	if err != nil {
		return err
	}

	share.LastUsedAt = time.Now()
	return fs.SaveShare(share)
}

// MemoryStorage implements Storage using in-memory map (for testing)
type MemoryStorage struct {
	shares map[string]*ShareData
	mu     sync.RWMutex
}

// NewMemoryStorage creates a new in-memory storage
func NewMemoryStorage() *MemoryStorage {
	return &MemoryStorage{
		shares: make(map[string]*ShareData),
	}
}

// SaveShare saves a share in memory
func (ms *MemoryStorage) SaveShare(share *ShareData) error {
	ms.mu.Lock()
	defer ms.mu.Unlock()
	ms.shares[share.KeysetID] = share
	return nil
}

// GetShare retrieves a share from memory
func (ms *MemoryStorage) GetShare(keysetID string) (*ShareData, error) {
	ms.mu.RLock()
	defer ms.mu.RUnlock()
	share, ok := ms.shares[keysetID]
	if !ok {
		return nil, fmt.Errorf("share not found: %s", keysetID)
	}
	return share, nil
}

// DeleteShare removes a share from memory
func (ms *MemoryStorage) DeleteShare(keysetID string) error {
	ms.mu.Lock()
	defer ms.mu.Unlock()
	delete(ms.shares, keysetID)
	return nil
}

// ListShares returns all keyset IDs
func (ms *MemoryStorage) ListShares() ([]string, error) {
	ms.mu.RLock()
	defer ms.mu.RUnlock()
	var keysetIDs []string
	for id := range ms.shares {
		keysetIDs = append(keysetIDs, id)
	}
	return keysetIDs, nil
}

// UpdateShareLastUsed updates the last used timestamp
func (ms *MemoryStorage) UpdateShareLastUsed(keysetID string) error {
	ms.mu.Lock()
	defer ms.mu.Unlock()
	share, ok := ms.shares[keysetID]
	if !ok {
		return fmt.Errorf("share not found: %s", keysetID)
	}
	share.LastUsedAt = time.Now()
	return nil
}
