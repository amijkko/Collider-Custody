//go:build ignore

package main

import (
	"encoding/json"
	"fmt"
	"os"
	"time"

	"github.com/bnb-chain/tss-lib/v2/ecdsa/keygen"
)

func main() {
	fmt.Println("Generating pre-params (this takes 30-60 seconds)...")
	start := time.Now()

	preParams, err := keygen.GeneratePreParams(5 * time.Minute)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("Generated in %v\n", time.Since(start))

	data := map[string]string{
		"PaillierSK_N":       preParams.PaillierSK.N.String(),
		"PaillierSK_LambdaN": preParams.PaillierSK.LambdaN.String(),
		"PaillierSK_PhiN":    preParams.PaillierSK.PhiN.String(),
		"PaillierSK_P":       preParams.PaillierSK.P.String(),
		"PaillierSK_Q":       preParams.PaillierSK.Q.String(),
		"NTildei":            preParams.NTildei.String(),
		"H1i":                preParams.H1i.String(),
		"H2i":                preParams.H2i.String(),
	}

	jsonData, _ := json.MarshalIndent(data, "", "  ")
	fmt.Println(string(jsonData))
	os.WriteFile("preparams.json", jsonData, 0644)
}
