package main

import (
	"crypto/ecdsa"
	"crypto/rand"
	"fmt"

	"github.com/ethereum/go-ethereum/crypto"
)

func main() {
	privateKey, err := ecdsa.GenerateKey(crypto.S256(), rand.Reader)
	if err != nil {
		panic(err)
	}

	privateKeyBytes := crypto.FromECDSA(privateKey)
	publicKey := privateKey.Public().(*ecdsa.PublicKey)
	address := crypto.PubkeyToAddress(*publicKey)

	fmt.Println("============================================================")
	fmt.Println("E2E FUNDING WALLET (EOA)")
	fmt.Println("============================================================")
	fmt.Printf("Address:     %s\n", address.Hex())
	fmt.Printf("Private Key: 0x%x\n", privateKeyBytes)
	fmt.Println("============================================================")
	fmt.Println("")
	fmt.Println("Send Sepolia ETH to this address.")
}
