package com.example.oteltest;

import java.util.Random;
import java.util.concurrent.TimeUnit;

public class Main {
    private static final Random random = new Random();

    public static void main(String[] args) throws InterruptedException {
        System.out.println("Starting OpenTelemetry Test Application...");
        System.out.println("Service name: otel-test-service");
        
        int iteration = 0;
        while (true) {
            iteration++;
            System.out.println("\n=== Iteration " + iteration + " ===");
            
            try {
                processOrder(iteration);
                Thread.sleep(3000);
            } catch (Exception e) {
                System.err.println("Error in iteration " + iteration + ": " + e.getMessage());
                e.printStackTrace();
            }
        }
    }

    private static void processOrder(int orderId) throws InterruptedException {
        System.out.println("Processing order: " + orderId);
        
        validateOrder(orderId);
        checkInventory(orderId);
        calculatePrice(orderId);
        saveOrder(orderId);
        
        System.out.println("Order " + orderId + " completed successfully");
    }

    private static void validateOrder(int orderId) throws InterruptedException {
        System.out.println("  -> Validating order " + orderId);
        Thread.sleep(random.nextInt(100) + 50);
        
        if (random.nextInt(20) == 0) {
            throw new RuntimeException("Validation failed for order " + orderId);
        }
    }

    private static void checkInventory(int orderId) throws InterruptedException {
        System.out.println("  -> Checking inventory for order " + orderId);
        Thread.sleep(random.nextInt(150) + 100);
    }

    private static void calculatePrice(int orderId) throws InterruptedException {
        System.out.println("  -> Calculating price for order " + orderId);
        Thread.sleep(random.nextInt(80) + 30);
    }

    private static void saveOrder(int orderId) throws InterruptedException {
        System.out.println("  -> Saving order " + orderId);
        Thread.sleep(random.nextInt(120) + 80);
    }
}