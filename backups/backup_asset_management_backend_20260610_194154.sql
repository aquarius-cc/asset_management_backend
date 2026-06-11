-- MySQL dump 10.13  Distrib 8.0.41, for Win64 (x86_64)
--
-- Host: localhost    Database: asset_management_backend
-- ------------------------------------------------------
-- Server version	8.0.41

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `am_asset`
--

DROP TABLE IF EXISTS `am_asset`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `am_asset` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `is_deleted` tinyint(1) NOT NULL,
  `asset_recordcode` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `asset_code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `asset_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `asset_purchase_price` decimal(10,2) NOT NULL,
  `asset_purchase_number` int NOT NULL,
  `asset_unit` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `asset_brand` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `asset_specification` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `asset_purchase_date` date NOT NULL,
  `asset_warranty_period` int DEFAULT NULL,
  `asset_entry_date` date NOT NULL,
  `asset_using_location` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `asset_current_status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `asset_description` longtext COLLATE utf8mb4_unicode_ci,
  `asset_applicant_jobcode_id` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `asset_entry_person_jobcode_id` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `asset_manager_jobcode_id` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `asset_type_code_id` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `asset_contract_code` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `asset_storage_code_id` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `asset_code` (`asset_code`),
  UNIQUE KEY `asset_recordcode` (`asset_recordcode`),
  KEY `am_asset_asset_r_b55e31_idx` (`asset_recordcode`),
  KEY `am_asset_asset_c_5d1ace_idx` (`asset_code`),
  KEY `am_asset_asset_c_df414a_idx` (`asset_current_status`),
  KEY `am_asset_asset_t_cc00c5_idx` (`asset_type_code_id`),
  KEY `am_asset_asset_s_51c492_idx` (`asset_storage_code_id`),
  KEY `am_asset_asset_applicant_jobc_acd3b933_fk_user_data` (`asset_applicant_jobcode_id`),
  KEY `am_asset_asset_entry_person_j_66483109_fk_user_data` (`asset_entry_person_jobcode_id`),
  KEY `am_asset_asset_manager_jobcod_585b0c02_fk_user_data` (`asset_manager_jobcode_id`),
  KEY `am_asset_asset_current_status_24cf1a76` (`asset_current_status`),
  KEY `am_asset_created_9d56c2_idx` (`created_at` DESC),
  KEY `idx_asset_type_status` (`asset_type_code_id`,`asset_current_status`),
  KEY `idx_asset_storage_status` (`asset_storage_code_id`,`asset_current_status`),
  KEY `idx_asset_contract_status` (`asset_contract_code`,`asset_current_status`),
  CONSTRAINT `am_asset_asset_applicant_jobc_acd3b933_fk_user_data` FOREIGN KEY (`asset_applicant_jobcode_id`) REFERENCES `user_database_table` (`employee_jobcode`),
  CONSTRAINT `am_asset_asset_contract_code_f16006f7_fk_am_contra` FOREIGN KEY (`asset_contract_code`) REFERENCES `am_contract` (`contract_code`),
  CONSTRAINT `am_asset_asset_entry_person_j_66483109_fk_user_data` FOREIGN KEY (`asset_entry_person_jobcode_id`) REFERENCES `user_database_table` (`employee_jobcode`),
  CONSTRAINT `am_asset_asset_manager_jobcod_585b0c02_fk_user_data` FOREIGN KEY (`asset_manager_jobcode_id`) REFERENCES `user_database_table` (`employee_jobcode`),
  CONSTRAINT `am_asset_asset_storage_code_i_0361e7e7_fk_am_storag` FOREIGN KEY (`asset_storage_code_id`) REFERENCES `am_storage` (`storage_code`),
  CONSTRAINT `am_asset_asset_type_code_id_275116f3_fk_am_asset_` FOREIGN KEY (`asset_type_code_id`) REFERENCES `am_asset_type` (`asset_type_code`)
) ENGINE=InnoDB AUTO_INCREMENT=24 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `am_asset`
--

LOCK TABLES `am_asset` WRITE;
/*!40000 ALTER TABLE `am_asset` DISABLE KEYS */;
INSERT INTO `am_asset` VALUES (1,'2026-05-21 14:24:15.808984','2026-05-21 14:24:15.809022',1,0,'Entry202605210000008CC40639','ASSET-ZDDN-000002','办公电脑一',7168.00,93,'台','戴尔','Optiplex 7410','2023-03-01',3,'2026-04-13',NULL,'in_store','一体式计算机',NULL,'A03949',NULL,'ZD-JSJ-YTJ','12-SC-16-01','C-304'),(2,'2026-05-21 14:24:15.815351','2026-05-23 07:29:42.581882',1,1,'Entry202605210000000034D780','ASSET-ZDDN-000001','办公电脑一',7168.00,93,'台','戴尔','Optiplex 7410','2023-03-01',3,'2026-04-13',NULL,'damaged','一体式计算机',NULL,'A03949',NULL,'ZD-JSJ-YTJ','12-SC-16-01','C-304'),(3,'2026-05-21 14:24:15.816906','2026-05-21 14:24:15.816956',1,0,'Entry202605210000003601EED3','ASSET-ZDDN-000004','办公电脑一',7168.00,93,'台','戴尔','Optiplex 7410','2023-03-01',3,'2026-04-13',NULL,'in_store','一体式计算机',NULL,'A03949',NULL,'ZD-JSJ-YTJ','12-SC-16-01','C-304'),(4,'2026-05-21 14:24:15.947071','2026-05-21 14:24:15.947104',1,0,'Entry20260521000000EC305631','ASSET-ZDDN-000005','办公电脑一',7168.00,93,'台','戴尔','Optiplex 7410','2023-03-01',3,'2026-04-13',NULL,'in_store','一体式计算机',NULL,'A03949',NULL,'ZD-JSJ-YTJ','12-SC-16-01','C-304'),(5,'2026-05-21 14:24:15.957030','2026-05-21 14:24:15.957063',1,0,'Entry202605210000003014F49F','ASSET-ZDDN-000006','办公电脑一',7168.00,93,'台','戴尔','Optiplex 7410','2023-03-01',3,'2026-04-13',NULL,'in_store','一体式计算机',NULL,'A03949',NULL,'ZD-JSJ-YTJ','12-SC-16-01','C-304'),(6,'2026-05-21 14:24:16.067460','2026-05-21 14:24:16.067497',1,0,'Entry20260521000000361B6538','ASSET-ZDDN-000010','办公电脑一',7168.00,93,'台','戴尔','Optiplex 7410','2023-03-01',3,'2026-04-13',NULL,'in_store','一体式计算机',NULL,'A03949',NULL,'ZD-JSJ-YTJ','12-SC-16-01','C-304'),(7,'2026-05-21 14:24:16.073368','2026-05-21 14:24:16.073401',1,0,'Entry20260521000000DBECCE9C','ASSET-ZDDN-000011','办公电脑一',7168.00,93,'台','戴尔','Optiplex 7410','2023-03-01',3,'2026-04-13',NULL,'in_store','一体式计算机',NULL,'A03949',NULL,'ZD-JSJ-YTJ','12-SC-16-01','C-304'),(8,'2026-05-21 14:24:16.223939','2026-05-21 14:24:16.223978',1,0,'Entry20260521000000AEED36FB','ASSET-ZDDN-000015','办公电脑一',7168.00,93,'台','戴尔','Optiplex 7410','2023-03-01',3,'2026-04-13',NULL,'in_store','一体式计算机',NULL,'A03949',NULL,'ZD-JSJ-YTJ','12-SC-16-01','C-304'),(9,'2026-05-21 14:24:16.232220','2026-05-21 14:24:16.232258',1,0,'Entry20260521000000BAB903AE','ASSET-ZDDN-000018','办公电脑一',7168.00,93,'台','戴尔','Optiplex 7410','2023-03-01',3,'2026-04-13',NULL,'recycled_pending','一体式计算机',NULL,'A03949','A03949','ZD-JSJ-YTJ','12-SC-16-01','B-606'),(10,'2026-05-21 14:24:16.367185','2026-05-21 14:24:16.367226',1,0,'Entry20260521000000537CE9A3','ASSET-ZDDN-000020','办公电脑一',7168.00,93,'台','戴尔','Optiplex 7410','2023-03-01',3,'2026-04-13',NULL,'damaged','一体式计算机',NULL,'A03949',NULL,'ZD-JSJ-YTJ','12-SC-16-01','B-606'),(11,'2026-06-05 02:06:38.240306','2026-06-05 02:06:38.240362',1,0,'Entry20260605000000E9408405','ASSET-hardware-ZD-JSJ-YTJ-20260605-2OWXRP-0001','信创电脑',10000.00,3,'套','攀升','龙芯','2026-06-01',3,'2026-06-05','','in_store','',NULL,'A03949',NULL,'ZD-JSJ-YTJ','12-SC-16-01','B-606'),(12,'2026-06-05 02:06:38.274003','2026-06-05 02:06:38.274062',1,0,'Entry20260605000000A905D651','ASSET-hardware-ZD-JSJ-YTJ-20260605-2OWXRP-0002','信创电脑',10000.00,3,'套','攀升','龙芯','2026-06-01',3,'2026-06-05','','in_store','',NULL,'A03949',NULL,'ZD-JSJ-YTJ','12-SC-16-01','B-606'),(13,'2026-06-05 02:06:38.292791','2026-06-05 02:06:38.292851',1,0,'Entry202606050000009A28C897','ASSET-hardware-ZD-JSJ-YTJ-20260605-2OWXRP-0003','信创电脑',10000.00,3,'套','攀升','龙芯','2026-06-01',3,'2026-06-05','','in_store','',NULL,'A03949',NULL,'ZD-JSJ-YTJ','12-SC-16-01','B-606'),(14,'2026-06-05 02:06:59.316040','2026-06-05 02:06:59.316089',1,0,'Entry20260605000000BA6F9D40','ASSET-hardware-ZD-JSJ-YTJ-20260605-7JGFX3-0001','信创电脑',10000.00,3,'套','攀升','龙芯','2026-06-01',3,'2026-06-05','','in_store','',NULL,'A03949',NULL,'ZD-JSJ-YTJ','12-SC-16-01','B-606'),(15,'2026-06-05 02:06:59.332133','2026-06-05 02:06:59.332176',1,0,'Entry202606050000005CB1DC19','ASSET-hardware-ZD-JSJ-YTJ-20260605-7JGFX3-0002','信创电脑',10000.00,3,'套','攀升','龙芯','2026-06-01',3,'2026-06-05','','in_store','',NULL,'A03949',NULL,'ZD-JSJ-YTJ','12-SC-16-01','B-606'),(16,'2026-06-05 02:06:59.345498','2026-06-05 02:06:59.345533',1,0,'Entry2026060500000027B69DAC','ASSET-hardware-ZD-JSJ-YTJ-20260605-7JGFX3-0003','信创电脑',10000.00,3,'套','攀升','龙芯','2026-06-01',3,'2026-06-05','','in_store','',NULL,'A03949',NULL,'ZD-JSJ-YTJ','12-SC-16-01','B-606'),(17,'2026-06-05 15:17:16.872524','2026-06-05 15:17:16.872581',1,0,'Entry20260605000000C27F53E8','ASSET-hardware-ZD-JSJ-YTJ-20260605-XLPLPH-0001','信创电脑二',9000.00,2,'台','浪潮','海光 C86','2025-01-10',3,'2025-01-15',NULL,'in_store','信创电脑',NULL,'A03949',NULL,'ZD-JSJ-YTJ','12-SC-16-01','B-606'),(18,'2026-06-05 15:17:16.919758','2026-06-05 15:17:16.919812',1,0,'Entry20260605000000AA09B3F4','ASSET-hardware-ZD-JSJ-YTJ-20260605-XLPLPH-0002','信创电脑二',9000.00,2,'台','浪潮','海光 C86','2025-01-10',3,'2025-01-15',NULL,'in_store','信创电脑',NULL,'A03949',NULL,'ZD-JSJ-YTJ','12-SC-16-01','B-606'),(19,'2026-06-05 15:17:16.991587','2026-06-05 15:17:16.991628',1,0,'Entry202606050000001D41D45D','ASSET-hardware-HYYPSB-20260605-GEEZQ4-0001','功放',16000.00,3,'台','雅马哈','雅马哈 P10','2025-01-10',3,'2025-01-15',NULL,'in_store','会议系统设备',NULL,'A03949',NULL,'HYYPSB','12-SC-16-01','B-606'),(20,'2026-06-05 15:17:17.019401','2026-06-05 15:17:17.019489',1,0,'Entry202606050000001D2625BA','ASSET-hardware-HYYPSB-20260605-GEEZQ4-0002','功放',16000.00,3,'台','雅马哈','雅马哈 P10','2025-01-10',3,'2025-01-15',NULL,'in_store','会议系统设备',NULL,'A03949',NULL,'HYYPSB','12-SC-16-01','B-606'),(21,'2026-06-05 15:17:17.036307','2026-06-05 15:17:17.036341',1,0,'Entry20260605000000F3C72AB1','ASSET-hardware-HYYPSB-20260605-GEEZQ4-0003','功放',16000.00,3,'台','雅马哈','雅马哈 P10','2025-01-10',3,'2025-01-15','B栋10楼','recycled_pending','会议系统设备','A03949','A03949','A03949','HYYPSB','12-SC-16-01',NULL),(22,'2026-06-05 15:17:17.102802','2026-06-05 15:17:17.102842',1,0,'Entry20260605000000CF486EF0','ASSET-hardware-WLSB-20260605-BY0GQQ-0001','交换机',800.00,1,'台','华为','8口','2025-01-10',3,'2025-01-15',NULL,'in_store','网络设备',NULL,'A03949',NULL,'WLSB','12-SC-16-01','B-606'),(23,'2026-06-05 15:22:46.483790','2026-06-06 12:18:42.016817',1,1,'Entry20260605000000FED71194','ASSET-hardware-WLSB-20260605-Q7YRDT-0001','交换机',800.00,1,'台','华为','8口','2025-01-10',3,'2025-01-15',NULL,'in_store','网络设备',NULL,'A03949',NULL,'WLSB','12-SC-16-01','B-606');
/*!40000 ALTER TABLE `am_asset` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `am_asset_operation_log`
--

DROP TABLE IF EXISTS `am_asset_operation_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `am_asset_operation_log` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `asset_code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `operation_type` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `operation_time` datetime(6) NOT NULL,
  `operator_jobcode` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `operator_name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `before_data` json DEFAULT NULL,
  `after_data` json DEFAULT NULL,
  `description` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `related_record_code` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `related_record_type` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `ip_address` char(39) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `logging_id` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `am_asset_operation_log_logging_id_0202afcb_uniq` (`logging_id`),
  KEY `am_asset_op_asset_c_53fc2d_idx` (`asset_code`,`operation_time` DESC),
  KEY `am_asset_op_operati_c5e024_idx` (`operation_type`,`operation_time` DESC),
  KEY `am_asset_op_operato_b047bf_idx` (`operator_jobcode`,`operation_time` DESC),
  KEY `am_asset_op_asset_c_d227ca_idx` (`asset_code`,`operation_type`),
  KEY `am_asset_operation_log_asset_code_67c59443` (`asset_code`),
  KEY `am_asset_operation_log_operation_type_f54d2cab` (`operation_type`),
  KEY `am_asset_operation_log_operation_time_cabb7867` (`operation_time`)
) ENGINE=InnoDB AUTO_INCREMENT=35 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `am_asset_operation_log`
--

LOCK TABLES `am_asset_operation_log` WRITE;
/*!40000 ALTER TABLE `am_asset_operation_log` DISABLE KEYS */;
INSERT INTO `am_asset_operation_log` VALUES (33,'ASSET-hardware-HYYPSB-20260605-GEEZQ4-0003','out','2026-06-09 14:26:33.942458','A03949',NULL,'{\"asset_current_status\": \"in_store\"}','{\"asset_current_status\": \"in_use\"}','资产出库发放: OUT-20260609-A5087FF6','OUT-20260609-A5087FF6','out',NULL,'out-Log-20260609-1WIKHHZE'),(34,'ASSET-hardware-HYYPSB-20260605-GEEZQ4-0003','recycle','2026-06-09 15:30:02.773408',NULL,NULL,'{\"asset_current_status\": \"in_use\"}','{\"asset_current_status\": \"recycled_pending\"}','资产回收: RECYCLE-20260609-LJ361Y10','RECYCLE-20260609-LJ361Y10','recycle',NULL,'recycle-Log-20260609-694JFF6C');
/*!40000 ALTER TABLE `am_asset_operation_log` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `am_asset_type`
--

DROP TABLE IF EXISTS `am_asset_type`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `am_asset_type` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `is_deleted` tinyint(1) NOT NULL,
  `asset_type_code` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `asset_type_secondary` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `asset_type_primary` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `asset_type_category` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `asset_type_description` longtext COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`),
  UNIQUE KEY `asset_type_code` (`asset_type_code`),
  KEY `am_asset_ty_asset_t_cb5144_idx` (`asset_type_code`),
  KEY `am_asset_ty_asset_t_3bc5d5_idx` (`asset_type_category`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `am_asset_type`
--

LOCK TABLES `am_asset_type` WRITE;
/*!40000 ALTER TABLE `am_asset_type` DISABLE KEYS */;
INSERT INTO `am_asset_type` VALUES (1,'2026-05-20 14:24:22.650516','2026-05-20 14:41:08.187553',1,1,'ZDJSJ','一体机','终端计算机','hardware',NULL),(2,'2026-05-20 14:29:08.066433','2026-05-20 14:41:06.594323',1,1,'ZDDYJ-LCDYJ','楼层打印机','终端打印机','hardware',NULL),(3,'2026-05-20 14:31:08.403477','2026-05-20 14:41:04.753834',1,1,'WL-LCJHJ','楼层交换机','网络设备','hardware',NULL),(4,'2026-05-20 14:42:49.897736','2026-05-20 14:42:49.897789',1,0,'ZD-JSJ-YTJ','一体机','终端计算机','hardware','一体式计算机'),(5,'2026-05-20 14:52:16.468145','2026-05-20 14:52:16.468208',1,0,'AST-001','服务器','电子设备','hardware',NULL),(7,'2026-05-20 14:52:18.184893','2026-05-20 14:52:18.184940',1,0,'JFSB','服务器','机房设备','hardware',NULL),(8,'2026-05-20 14:52:18.196102','2026-05-20 14:52:18.196152',1,0,'HYYPSB','功放','会议音频设备','hardware',NULL),(9,'2026-06-05 15:10:30.514265','2026-06-05 15:10:30.514317',1,0,'WLSB','网络交换机','网络设备','hardware','8口网络交换机');
/*!40000 ALTER TABLE `am_asset_type` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `am_contract`
--

DROP TABLE IF EXISTS `am_contract`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `am_contract` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `is_deleted` tinyint(1) NOT NULL,
  `contract_code` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `contract_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `contract_type` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `contract_price` decimal(10,2) NOT NULL,
  `contract_supplier` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `contract_signing_date` date NOT NULL,
  `contract_warranty_period` int NOT NULL,
  `contract_preliminary_acceptance_date` date DEFAULT NULL,
  `contract_final_acceptance_date` date DEFAULT NULL,
  `contract_settlment_status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `contract_settlment_price` decimal(10,2) DEFAULT NULL,
  `contract_paid_count_number` int NOT NULL,
  `contract_paid_price` decimal(10,2) DEFAULT NULL,
  `contract_paid_record` longtext COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`),
  UNIQUE KEY `contract_code` (`contract_code`),
  UNIQUE KEY `contract_name` (`contract_name`),
  KEY `am_contract_contrac_ebab44_idx` (`contract_code`),
  KEY `am_contract_contrac_e52d21_idx` (`contract_type`),
  KEY `am_contract_contrac_8372cb_idx` (`contract_settlment_status`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `am_contract`
--

LOCK TABLES `am_contract` WRITE;
/*!40000 ALTER TABLE `am_contract` DISABLE KEYS */;
INSERT INTO `am_contract` VALUES (1,'2026-05-20 13:59:34.240186','2026-05-20 13:59:34.241107',1,0,'VI2-SC-06-01','武汉市轨道交通6号线二期工程信息设备采购项目','purchase',3127357.00,'浙江浙大中控信息技术有限公司','2019-12-01',0,NULL,NULL,'pending',0.00,0,0.00,''),(2,'2026-05-20 13:59:34.250766','2026-05-20 13:59:34.250901',1,0,'CT-2025-001','服务器采购合同','purchase',100000.00,'XX科技有限公司','2025-01-15',3,NULL,NULL,'pending',50000.00,1,50000.00,'2025-01-20支付首付款50%'),(3,'2026-05-20 13:59:34.258286','2026-05-20 13:59:34.258392',1,0,'GS-JZ-0814','武汉地铁集团多媒体服务项目','service',482260.00,'武汉米易科技有限公司','2018-01-01',0,NULL,NULL,'pending',0.00,0,0.00,''),(4,'2026-05-20 13:59:34.467181','2026-05-20 13:59:34.467281',1,0,'GS-JZ-1306','武汉地铁集团涉密计算机类设备采购合同','purchase',18080.00,'武汉市德发电子信息有限责任公司','2018-09-01',0,NULL,NULL,'pending',0.00,0,0.00,''),(5,'2026-05-20 13:59:34.471633','2026-05-20 13:59:34.471699',1,0,'GS-JZ-1344','市国资委建设视频会议系统统一平台设备采购合同','purchase',52689.00,'湖北蓝辰科技有限公司','2020-09-01',0,NULL,NULL,'pending',0.00,0,0.00,''),(6,'2026-05-20 13:59:34.480012','2026-05-20 13:59:34.480073',1,0,'12-SC-16-01','武汉市轨道交通12号线工程信息设备采购项目','purchase',2850000.00,'烽火通信科技股份有限公司','2023-12-01',0,NULL,NULL,'pending',0.00,0,0.00,'');
/*!40000 ALTER TABLE `am_contract` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `am_damaged_asset`
--

DROP TABLE IF EXISTS `am_damaged_asset`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `am_damaged_asset` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `is_deleted` tinyint(1) NOT NULL,
  `damaged_asset_number` int NOT NULL,
  `damaged_date` date DEFAULT NULL,
  `approval_status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `damaged_asset_description` longtext COLLATE utf8mb4_unicode_ci,
  `approver_id` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `damaged_asset_code_id` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `damaged_asset_code_id` (`damaged_asset_code_id`),
  KEY `am_damaged__damaged_2b04dc_idx` (`damaged_asset_code_id`),
  KEY `am_damaged__approva_401841_idx` (`approval_status`),
  KEY `am_damaged_asset_approver_id_c7c606c6_fk_user_data` (`approver_id`),
  CONSTRAINT `am_damaged_asset_approver_id_c7c606c6_fk_user_data` FOREIGN KEY (`approver_id`) REFERENCES `user_database_table` (`employee_jobcode`),
  CONSTRAINT `am_damaged_asset_damaged_asset_code_id_0b719026_fk` FOREIGN KEY (`damaged_asset_code_id`) REFERENCES `am_asset` (`asset_code`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `am_damaged_asset`
--

LOCK TABLES `am_damaged_asset` WRITE;
/*!40000 ALTER TABLE `am_damaged_asset` DISABLE KEYS */;
INSERT INTO `am_damaged_asset` VALUES (4,'2026-06-07 12:20:51.681724','2026-06-07 12:20:51.681775',1,0,1,'2026-06-07','pending',NULL,NULL,'ASSET-ZDDN-000018');
/*!40000 ALTER TABLE `am_damaged_asset` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `am_hard_disk_sn`
--

DROP TABLE IF EXISTS `am_hard_disk_sn`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `am_hard_disk_sn` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `is_deleted` tinyint(1) NOT NULL,
  `harddisk_number` int NOT NULL,
  `harddisk_no` int NOT NULL,
  `harddisk_sn_code` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `harddisk_type` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `harddisk_sn_description` longtext COLLATE utf8mb4_unicode_ci,
  `harddisk_status` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL,
  `asset_code_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `harddisk_sn_code` (`harddisk_sn_code`),
  KEY `am_hard_dis_harddis_e1d258_idx` (`harddisk_sn_code`),
  KEY `am_hard_dis_asset_c_7977e2_idx` (`asset_code_id`),
  KEY `am_hard_dis_harddis_d99692_idx` (`harddisk_status`),
  CONSTRAINT `am_hard_disk_sn_asset_code_id_44a1fa83_fk` FOREIGN KEY (`asset_code_id`) REFERENCES `am_asset` (`asset_code`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `am_hard_disk_sn`
--

LOCK TABLES `am_hard_disk_sn` WRITE;
/*!40000 ALTER TABLE `am_hard_disk_sn` DISABLE KEYS */;
INSERT INTO `am_hard_disk_sn` VALUES (2,'2026-06-03 14:28:16.451810','2026-06-03 14:28:16.451869',1,0,1,1,'SN8909JIO909','SSD','系统盘','active','ASSET-ZDDN-000002'),(3,'2026-06-04 00:46:06.225355','2026-06-04 00:46:06.225402',1,0,1,1,'SFDSG564654','HDD','数据盘','active','ASSET-ZDDN-000002');
/*!40000 ALTER TABLE `am_hard_disk_sn` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `am_out_asset`
--

DROP TABLE IF EXISTS `am_out_asset`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `am_out_asset` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `is_deleted` tinyint(1) NOT NULL,
  `outasset_recordcode` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `outasset_number` int NOT NULL,
  `return_date` date DEFAULT NULL,
  `outasset_date` date NOT NULL,
  `outasset_type` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `outasset_description` longtext COLLATE utf8mb4_unicode_ci,
  `outasset_code_id` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `outasset_previous_status` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `outasset_recordcode` (`outasset_recordcode`),
  KEY `am_out_asse_outasse_9060e3_idx` (`outasset_recordcode`),
  KEY `am_out_asse_outasse_50b277_idx` (`outasset_code_id`),
  KEY `am_out_asse_outasse_7cbbb7_idx` (`outasset_date`),
  CONSTRAINT `am_out_asset_outasset_code_id_1351f79f_fk` FOREIGN KEY (`outasset_code_id`) REFERENCES `am_asset` (`asset_code`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `am_out_asset`
--

LOCK TABLES `am_out_asset` WRITE;
/*!40000 ALTER TABLE `am_out_asset` DISABLE KEYS */;
INSERT INTO `am_out_asset` VALUES (6,'2026-06-06 12:21:01.989556','2026-06-06 12:21:01.989633',1,0,'OUT-20260606-3E2A377F',1,NULL,'2026-06-06','receive',NULL,'ASSET-hardware-HYYPSB-20260605-GEEZQ4-0003','in_store'),(7,'2026-06-09 14:26:33.926178','2026-06-09 14:26:33.926268',1,0,'OUT-20260609-A5087FF6',1,NULL,'2026-06-09','receive',NULL,'ASSET-hardware-HYYPSB-20260605-GEEZQ4-0003','recycled_pending');
/*!40000 ALTER TABLE `am_out_asset` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `am_recycle_asset`
--

DROP TABLE IF EXISTS `am_recycle_asset`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `am_recycle_asset` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `is_deleted` tinyint(1) NOT NULL,
  `recycle_asset_number` int NOT NULL,
  `recycle_asset_date` date NOT NULL,
  `recycle_asset_description` longtext COLLATE utf8mb4_unicode_ci,
  `outasset_recordcode_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `recycle_asset_code_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `recycle_record_code` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL,
  `operator_jobcode_id` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `outasset_recordcode_id` (`outasset_recordcode_id`),
  UNIQUE KEY `am_recycle_asset_recycle_record_code_01e31310_uniq` (`recycle_record_code`),
  KEY `am_recycle__outasse_c9582f_idx` (`outasset_recordcode_id`),
  KEY `am_recycle__recycle_6df88e_idx` (`recycle_asset_code_id`),
  KEY `am_recycle__recycle_3c3295_idx` (`recycle_record_code`),
  KEY `am_recycle_asset_operator_jobcode_id_f2f63da9_fk_user_data` (`operator_jobcode_id`),
  CONSTRAINT `am_recycle_asset_operator_jobcode_id_f2f63da9_fk_user_data` FOREIGN KEY (`operator_jobcode_id`) REFERENCES `user_database_table` (`employee_jobcode`),
  CONSTRAINT `am_recycle_asset_outasset_recordcode__87368337_fk_am_out_as` FOREIGN KEY (`outasset_recordcode_id`) REFERENCES `am_out_asset` (`outasset_recordcode`),
  CONSTRAINT `am_recycle_asset_recycle_asset_code_id_45dd689a_fk` FOREIGN KEY (`recycle_asset_code_id`) REFERENCES `am_asset` (`asset_code`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `am_recycle_asset`
--

LOCK TABLES `am_recycle_asset` WRITE;
/*!40000 ALTER TABLE `am_recycle_asset` DISABLE KEYS */;
INSERT INTO `am_recycle_asset` VALUES (8,'2026-06-06 15:24:05.429092','2026-06-06 15:24:05.429168',1,0,1,'2026-06-06',NULL,'OUT-20260606-3E2A377F','ASSET-hardware-HYYPSB-20260605-GEEZQ4-0003','RECYCLE-20260606-F6SGOR9D',NULL),(9,'2026-06-09 15:30:02.762801','2026-06-09 15:30:02.762860',1,0,1,'2026-06-09',NULL,'OUT-20260609-A5087FF6','ASSET-hardware-HYYPSB-20260605-GEEZQ4-0003','RECYCLE-20260609-LJ361Y10',NULL);
/*!40000 ALTER TABLE `am_recycle_asset` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `am_storage`
--

DROP TABLE IF EXISTS `am_storage`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `am_storage` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `is_deleted` tinyint(1) NOT NULL,
  `storage_code` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `storage_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `storage_address` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL,
  `storage_type` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `storage_description` longtext COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`),
  UNIQUE KEY `storage_code` (`storage_code`),
  UNIQUE KEY `storage_name` (`storage_name`),
  KEY `am_storage_storage_8e5c92_idx` (`storage_code`),
  KEY `am_storage_storage_a54307_idx` (`storage_type`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `am_storage`
--

LOCK TABLES `am_storage` WRITE;
/*!40000 ALTER TABLE `am_storage` DISABLE KEYS */;
INSERT INTO `am_storage` VALUES (1,'2026-05-20 13:28:01.399874','2026-05-20 13:28:01.399930',1,0,'C-304','新旧混合仓库','C栋304','newasset',''),(2,'2026-05-20 13:28:38.654821','2026-05-20 13:28:38.654866',1,0,'B-606','新旧混合仓库2','B栋606','newasset',''),(3,'2026-05-20 13:29:29.914697','2026-05-20 13:29:29.914745',1,0,'SJT-108','三金潭待报废仓库108','三金潭车辆段控制中心大楼1楼108','damaged',''),(4,'2026-05-20 13:29:58.838314','2026-05-20 13:29:58.838365',1,0,'SJT-114','三金潭待报废仓库114','三金潭车辆段控制中心大楼1楼114','damaged','');
/*!40000 ALTER TABLE `am_storage` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `am_unregistered_asset`
--

DROP TABLE IF EXISTS `am_unregistered_asset`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `am_unregistered_asset` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `is_deleted` tinyint(1) NOT NULL,
  `unregistered_code` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `scenario_type` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `discovery_date` date NOT NULL,
  `discovery_location` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL,
  `asset_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `asset_brand` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `asset_specification` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `estimated_value` decimal(10,2) DEFAULT NULL,
  `handle_type` varchar(30) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `handle_description` longtext COLLATE utf8mb4_unicode_ci,
  `approval_status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `approval_date` date DEFAULT NULL,
  `approval_remark` longtext COLLATE utf8mb4_unicode_ci,
  `attachments` json NOT NULL,
  `approver_jobcode_id` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `asset_type_code_id` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `discovery_person_jobcode_id` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `related_asset_code_id` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `result_asset_code_id` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `result_damaged_code_id` bigint DEFAULT NULL,
  `result_recycle_code_id` bigint DEFAULT NULL,
  `target_storage_code_id` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unregistered_code` (`unregistered_code`),
  KEY `am_unregistered_asse_approver_jobcode_id_5080d1a1_fk_user_data` (`approver_jobcode_id`),
  KEY `am_unregistered_asse_asset_type_code_id_1794f161_fk_am_asset_` (`asset_type_code_id`),
  KEY `am_unregistered_asse_result_damaged_code__6a352cc5_fk_am_damage` (`result_damaged_code_id`),
  KEY `am_unregistered_asse_result_recycle_code__23247e0f_fk_am_recycl` (`result_recycle_code_id`),
  KEY `am_unregistered_asse_target_storage_code__ac45c13b_fk_am_storag` (`target_storage_code_id`),
  KEY `am_unregist_unregis_29b05d_idx` (`unregistered_code`),
  KEY `am_unregist_scenari_297ba8_idx` (`scenario_type`),
  KEY `am_unregist_approva_b9e098_idx` (`approval_status`),
  KEY `am_unregist_discove_62c158_idx` (`discovery_person_jobcode_id`),
  KEY `am_unregist_discove_c38d4e_idx` (`discovery_person_jobcode_id`,`approval_status`),
  KEY `am_unregistered_asset_related_asset_code_id_43094659_fk` (`related_asset_code_id`),
  KEY `am_unregistered_asset_result_asset_code_id_24baa633_fk` (`result_asset_code_id`),
  CONSTRAINT `am_unregistered_asse_approver_jobcode_id_5080d1a1_fk_user_data` FOREIGN KEY (`approver_jobcode_id`) REFERENCES `user_database_table` (`employee_jobcode`),
  CONSTRAINT `am_unregistered_asse_asset_type_code_id_1794f161_fk_am_asset_` FOREIGN KEY (`asset_type_code_id`) REFERENCES `am_asset_type` (`asset_type_code`),
  CONSTRAINT `am_unregistered_asse_discovery_person_job_a77d3d39_fk_user_data` FOREIGN KEY (`discovery_person_jobcode_id`) REFERENCES `user_database_table` (`employee_jobcode`),
  CONSTRAINT `am_unregistered_asse_result_damaged_code__6a352cc5_fk_am_damage` FOREIGN KEY (`result_damaged_code_id`) REFERENCES `am_damaged_asset` (`id`),
  CONSTRAINT `am_unregistered_asse_result_recycle_code__23247e0f_fk_am_recycl` FOREIGN KEY (`result_recycle_code_id`) REFERENCES `am_recycle_asset` (`id`),
  CONSTRAINT `am_unregistered_asse_target_storage_code__ac45c13b_fk_am_storag` FOREIGN KEY (`target_storage_code_id`) REFERENCES `am_storage` (`storage_code`),
  CONSTRAINT `am_unregistered_asset_related_asset_code_id_43094659_fk` FOREIGN KEY (`related_asset_code_id`) REFERENCES `am_asset` (`asset_code`),
  CONSTRAINT `am_unregistered_asset_result_asset_code_id_24baa633_fk` FOREIGN KEY (`result_asset_code_id`) REFERENCES `am_asset` (`asset_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `am_unregistered_asset`
--

LOCK TABLES `am_unregistered_asset` WRITE;
/*!40000 ALTER TABLE `am_unregistered_asset` DISABLE KEYS */;
/*!40000 ALTER TABLE `am_unregistered_asset` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `am_waste_asset`
--

DROP TABLE IF EXISTS `am_waste_asset`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `am_waste_asset` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `is_deleted` tinyint(1) NOT NULL,
  `waste_asset_number` int NOT NULL,
  `waste_asset_date` date NOT NULL,
  `waste_asset_description` longtext COLLATE utf8mb4_unicode_ci,
  `waste_asset_code_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_damaged_asset_id` bigint DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `waste_asset_code_id` (`waste_asset_code_id`),
  UNIQUE KEY `source_damaged_asset_id` (`source_damaged_asset_id`),
  KEY `am_waste_as_waste_a_a6cb33_idx` (`waste_asset_code_id`),
  KEY `am_waste_as_source__16c07e_idx` (`source_damaged_asset_id`),
  CONSTRAINT `am_waste_asset_source_damaged_asset_8eb19fb1_fk_am_damage` FOREIGN KEY (`source_damaged_asset_id`) REFERENCES `am_damaged_asset` (`id`),
  CONSTRAINT `am_waste_asset_waste_asset_code_id_67b8d544_fk` FOREIGN KEY (`waste_asset_code_id`) REFERENCES `am_asset` (`asset_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `am_waste_asset`
--

LOCK TABLES `am_waste_asset` WRITE;
/*!40000 ALTER TABLE `am_waste_asset` DISABLE KEYS */;
/*!40000 ALTER TABLE `am_waste_asset` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `auth_group`
--

DROP TABLE IF EXISTS `auth_group`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `auth_group` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `auth_group`
--

LOCK TABLES `auth_group` WRITE;
/*!40000 ALTER TABLE `auth_group` DISABLE KEYS */;
/*!40000 ALTER TABLE `auth_group` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `auth_group_permissions`
--

DROP TABLE IF EXISTS `auth_group_permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `auth_group_permissions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `group_id` int NOT NULL,
  `permission_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_group_permissions_group_id_permission_id_0cd325b0_uniq` (`group_id`,`permission_id`),
  KEY `auth_group_permissio_permission_id_84c5c92e_fk_auth_perm` (`permission_id`),
  CONSTRAINT `auth_group_permissio_permission_id_84c5c92e_fk_auth_perm` FOREIGN KEY (`permission_id`) REFERENCES `auth_permission` (`id`),
  CONSTRAINT `auth_group_permissions_group_id_b120cbf9_fk_auth_group_id` FOREIGN KEY (`group_id`) REFERENCES `auth_group` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `auth_group_permissions`
--

LOCK TABLES `auth_group_permissions` WRITE;
/*!40000 ALTER TABLE `auth_group_permissions` DISABLE KEYS */;
/*!40000 ALTER TABLE `auth_group_permissions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `auth_permission`
--

DROP TABLE IF EXISTS `auth_permission`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `auth_permission` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `content_type_id` int NOT NULL,
  `codename` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_permission_content_type_id_codename_01ab375a_uniq` (`content_type_id`,`codename`),
  CONSTRAINT `auth_permission_content_type_id_2f476e4b_fk_django_co` FOREIGN KEY (`content_type_id`) REFERENCES `django_content_type` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=121 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `auth_permission`
--

LOCK TABLES `auth_permission` WRITE;
/*!40000 ALTER TABLE `auth_permission` DISABLE KEYS */;
INSERT INTO `auth_permission` VALUES (1,'Can add log entry',19,'add_logentry'),(2,'Can change log entry',19,'change_logentry'),(3,'Can delete log entry',19,'delete_logentry'),(4,'Can view log entry',19,'view_logentry'),(5,'Can add permission',21,'add_permission'),(6,'Can change permission',21,'change_permission'),(7,'Can delete permission',21,'delete_permission'),(8,'Can view permission',21,'view_permission'),(9,'Can add group',20,'add_group'),(10,'Can change group',20,'change_group'),(11,'Can delete group',20,'delete_group'),(12,'Can view group',20,'view_group'),(13,'Can add content type',22,'add_contenttype'),(14,'Can change content type',22,'change_contenttype'),(15,'Can delete content type',22,'delete_contenttype'),(16,'Can view content type',22,'view_contenttype'),(17,'Can add session',23,'add_session'),(18,'Can change session',23,'change_session'),(19,'Can delete session',23,'delete_session'),(20,'Can view session',23,'view_session'),(21,'Can add 部门管理',24,'add_department'),(22,'Can change 部门管理',24,'change_department'),(23,'Can delete 部门管理',24,'delete_department'),(24,'Can view 部门管理',24,'view_department'),(25,'Can add 员工管理',25,'add_employee'),(26,'Can change 员工管理',25,'change_employee'),(27,'Can delete 员工管理',25,'delete_employee'),(28,'Can view 员工管理',25,'view_employee'),(29,'Can add 仓库管理',1,'add_storage'),(30,'Can change 仓库管理',1,'change_storage'),(31,'Can delete 仓库管理',1,'delete_storage'),(32,'Can view 仓库管理',1,'view_storage'),(33,'Can add 资产分类管理',3,'add_assettype'),(34,'Can change 资产分类管理',3,'change_assettype'),(35,'Can delete 资产分类管理',3,'delete_assettype'),(36,'Can view 资产分类管理',3,'view_assettype'),(37,'Can add 合同管理',5,'add_contract'),(38,'Can change 合同管理',5,'change_contract'),(39,'Can delete 合同管理',5,'delete_contract'),(40,'Can view 合同管理',5,'view_contract'),(41,'Can add 资产管理',7,'add_asset'),(42,'Can change 资产管理',7,'change_asset'),(43,'Can delete 资产管理',7,'delete_asset'),(44,'Can view 资产管理',7,'view_asset'),(45,'Can add 出库资产管理',9,'add_outasset'),(46,'Can change 出库资产管理',9,'change_outasset'),(47,'Can delete 出库资产管理',9,'delete_outasset'),(48,'Can view 出库资产管理',9,'view_outasset'),(49,'Can add 回收资产管理',11,'add_recycleasset'),(50,'Can change 回收资产管理',11,'change_recycleasset'),(51,'Can delete 回收资产管理',11,'delete_recycleasset'),(52,'Can view 回收资产管理',11,'view_recycleasset'),(53,'Can add 待报废资产管理',13,'add_damagedasset'),(54,'Can change 待报废资产管理',13,'change_damagedasset'),(55,'Can delete 待报废资产管理',13,'delete_damagedasset'),(56,'Can view 待报废资产管理',13,'view_damagedasset'),(57,'Can add 已报废资产管理',15,'add_wasteasset'),(58,'Can change 已报废资产管理',15,'change_wasteasset'),(59,'Can delete 已报废资产管理',15,'delete_wasteasset'),(60,'Can view 已报废资产管理',15,'view_wasteasset'),(61,'Can add 硬盘序列号管理',17,'add_harddisksn'),(62,'Can change 硬盘序列号管理',17,'change_harddisksn'),(63,'Can delete 硬盘序列号管理',17,'delete_harddisksn'),(64,'Can view 硬盘序列号管理',17,'view_harddisksn'),(65,'Can add 仓库管理(兼容)',2,'add_storagedatabasetable'),(66,'Can change 仓库管理(兼容)',2,'change_storagedatabasetable'),(67,'Can delete 仓库管理(兼容)',2,'delete_storagedatabasetable'),(68,'Can view 仓库管理(兼容)',2,'view_storagedatabasetable'),(69,'Can add 资产类型管理(兼容)',4,'add_assettypedatabasetable'),(70,'Can change 资产类型管理(兼容)',4,'change_assettypedatabasetable'),(71,'Can delete 资产类型管理(兼容)',4,'delete_assettypedatabasetable'),(72,'Can view 资产类型管理(兼容)',4,'view_assettypedatabasetable'),(73,'Can add 合同管理(兼容)',6,'add_contractdatabasetable'),(74,'Can change 合同管理(兼容)',6,'change_contractdatabasetable'),(75,'Can delete 合同管理(兼容)',6,'delete_contractdatabasetable'),(76,'Can view 合同管理(兼容)',6,'view_contractdatabasetable'),(77,'Can add 资产管理(兼容)',8,'add_assetdatabasetable'),(78,'Can change 资产管理(兼容)',8,'change_assetdatabasetable'),(79,'Can delete 资产管理(兼容)',8,'delete_assetdatabasetable'),(80,'Can view 资产管理(兼容)',8,'view_assetdatabasetable'),(81,'Can add 出库资产管理(兼容)',10,'add_outassetdatabasetable'),(82,'Can change 出库资产管理(兼容)',10,'change_outassetdatabasetable'),(83,'Can delete 出库资产管理(兼容)',10,'delete_outassetdatabasetable'),(84,'Can view 出库资产管理(兼容)',10,'view_outassetdatabasetable'),(85,'Can add 回收资产管理(兼容)',12,'add_recycleassetdatabasetable'),(86,'Can change 回收资产管理(兼容)',12,'change_recycleassetdatabasetable'),(87,'Can delete 回收资产管理(兼容)',12,'delete_recycleassetdatabasetable'),(88,'Can view 回收资产管理(兼容)',12,'view_recycleassetdatabasetable'),(89,'Can add 待报废资产管理(兼容)',14,'add_damagedassetdatabasetable'),(90,'Can change 待报废资产管理(兼容)',14,'change_damagedassetdatabasetable'),(91,'Can delete 待报废资产管理(兼容)',14,'delete_damagedassetdatabasetable'),(92,'Can view 待报废资产管理(兼容)',14,'view_damagedassetdatabasetable'),(93,'Can add 已报废资产管理(兼容)',16,'add_wasteassettable'),(94,'Can change 已报废资产管理(兼容)',16,'change_wasteassettable'),(95,'Can delete 已报废资产管理(兼容)',16,'delete_wasteassettable'),(96,'Can view 已报废资产管理(兼容)',16,'view_wasteassettable'),(97,'Can add 硬盘序列号管理(兼容)',18,'add_harddisksndatabasetable'),(98,'Can change 硬盘序列号管理(兼容)',18,'change_harddisksndatabasetable'),(99,'Can delete 硬盘序列号管理(兼容)',18,'delete_harddisksndatabasetable'),(100,'Can view 硬盘序列号管理(兼容)',18,'view_harddisksndatabasetable'),(101,'Can add 认证与用户管理',26,'add_authuser'),(102,'Can change 认证与用户管理',26,'change_authuser'),(103,'Can delete 认证与用户管理',26,'delete_authuser'),(104,'Can view 认证与用户管理',26,'view_authuser'),(105,'Can add 资产操作记录',27,'add_assetoperationlog'),(106,'Can change 资产操作记录',27,'change_assetoperationlog'),(107,'Can delete 资产操作记录',27,'delete_assetoperationlog'),(108,'Can view 资产操作记录',27,'view_assetoperationlog'),(109,'Can add Blacklisted Token',28,'add_blacklistedtoken'),(110,'Can change Blacklisted Token',28,'change_blacklistedtoken'),(111,'Can delete Blacklisted Token',28,'delete_blacklistedtoken'),(112,'Can view Blacklisted Token',28,'view_blacklistedtoken'),(113,'Can add Outstanding Token',29,'add_outstandingtoken'),(114,'Can change Outstanding Token',29,'change_outstandingtoken'),(115,'Can delete Outstanding Token',29,'delete_outstandingtoken'),(116,'Can view Outstanding Token',29,'view_outstandingtoken'),(117,'Can add 未登记资产管理',30,'add_unregisteredasset'),(118,'Can change 未登记资产管理',30,'change_unregisteredasset'),(119,'Can delete 未登记资产管理',30,'delete_unregisteredasset'),(120,'Can view 未登记资产管理',30,'view_unregisteredasset');
/*!40000 ALTER TABLE `auth_permission` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `auth_user_management_table`
--

DROP TABLE IF EXISTS `auth_user_management_table`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `auth_user_management_table` (
  `password` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL,
  `is_superuser` tinyint(1) NOT NULL,
  `auth_id` int NOT NULL AUTO_INCREMENT,
  `auth_username` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  `email` varchar(254) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `auth_is_active` tinyint(1) NOT NULL,
  `auth_is_staff` tinyint(1) NOT NULL,
  `auth_date_create` datetime(6) NOT NULL,
  `auth_date_update` datetime(6) NOT NULL,
  `auth_phone` varchar(15) COLLATE utf8mb4_unicode_ci NOT NULL,
  `last_login` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`auth_id`),
  UNIQUE KEY `auth_username` (`auth_username`),
  UNIQUE KEY `auth_phone` (`auth_phone`),
  UNIQUE KEY `email` (`email`),
  KEY `auth_user_m_auth_us_008906_idx` (`auth_username`),
  KEY `auth_user_m_email_a42132_idx` (`email`),
  KEY `auth_user_m_auth_ph_7732d4_idx` (`auth_phone`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `auth_user_management_table`
--

LOCK TABLES `auth_user_management_table` WRITE;
/*!40000 ALTER TABLE `auth_user_management_table` DISABLE KEYS */;
INSERT INTO `auth_user_management_table` VALUES ('pbkdf2_sha256$1200000$s2xEZqKiQNNhhdFcBaHrru$bAdI28twv5nRcQi85E0+pqkAH+iEf0VukBPyAenK/xk=',1,3,'whdtadmin','whdt@123.com',1,1,'2026-05-08 15:36:26.270725','2026-05-08 15:36:26.270754','','2026-05-18 02:19:49.624351');
/*!40000 ALTER TABLE `auth_user_management_table` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `auth_user_management_table_groups`
--

DROP TABLE IF EXISTS `auth_user_management_table_groups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `auth_user_management_table_groups` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `authuser_id` int NOT NULL,
  `group_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_user_management_tab_authuser_id_group_id_978ca467_uniq` (`authuser_id`,`group_id`),
  KEY `auth_user_management_group_id_c6bbb5f5_fk_auth_grou` (`group_id`),
  CONSTRAINT `auth_user_management_authuser_id_d53e08ae_fk_auth_user` FOREIGN KEY (`authuser_id`) REFERENCES `auth_user_management_table` (`auth_id`),
  CONSTRAINT `auth_user_management_group_id_c6bbb5f5_fk_auth_grou` FOREIGN KEY (`group_id`) REFERENCES `auth_group` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `auth_user_management_table_groups`
--

LOCK TABLES `auth_user_management_table_groups` WRITE;
/*!40000 ALTER TABLE `auth_user_management_table_groups` DISABLE KEYS */;
/*!40000 ALTER TABLE `auth_user_management_table_groups` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `auth_user_management_table_user_permissions`
--

DROP TABLE IF EXISTS `auth_user_management_table_user_permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `auth_user_management_table_user_permissions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `authuser_id` int NOT NULL,
  `permission_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_user_management_tab_authuser_id_permission_i_3bef5039_uniq` (`authuser_id`,`permission_id`),
  KEY `auth_user_management_permission_id_5afb1c7a_fk_auth_perm` (`permission_id`),
  CONSTRAINT `auth_user_management_authuser_id_a3abfd8b_fk_auth_user` FOREIGN KEY (`authuser_id`) REFERENCES `auth_user_management_table` (`auth_id`),
  CONSTRAINT `auth_user_management_permission_id_5afb1c7a_fk_auth_perm` FOREIGN KEY (`permission_id`) REFERENCES `auth_permission` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `auth_user_management_table_user_permissions`
--

LOCK TABLES `auth_user_management_table_user_permissions` WRITE;
/*!40000 ALTER TABLE `auth_user_management_table_user_permissions` DISABLE KEYS */;
/*!40000 ALTER TABLE `auth_user_management_table_user_permissions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `department_database_table`
--

DROP TABLE IF EXISTS `department_database_table`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `department_database_table` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `department_code` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `department_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `department_information` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `sort_order` int NOT NULL,
  `level` int NOT NULL,
  `parent_code` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `department_code` (`department_code`),
  UNIQUE KEY `department_name` (`department_name`),
  KEY `idx_department_parent` (`parent_code`),
  KEY `idx_department_level` (`level`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `department_database_table`
--

LOCK TABLES `department_database_table` WRITE;
/*!40000 ALTER TABLE `department_database_table` DISABLE KEYS */;
INSERT INTO `department_database_table` VALUES (2,'JTGSLD','集团公司领导','欧阳潇',1,1,'WHDTJT'),(3,'JTXXGLZX','信息管理中心','刘肖阳',2,1,'WHDTJT'),(4,'JTCWB','财务部','熊铭',10,1,'WHDTJT'),(5,'JTQGB','企管部','尹奇',20,1,'WHDTJT'),(6,'JTSJFKB','审计风控部','袁媛',9,1,'WHDTJT'),(7,'JTJSGLZX','技术管理中心','刘彦君',1,1,'WHDTJT'),(8,'WHDTJT','武汉地铁集团有限公司','无',0,0,NULL);
/*!40000 ALTER TABLE `department_database_table` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `django_admin_log`
--

DROP TABLE IF EXISTS `django_admin_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `django_admin_log` (
  `id` int NOT NULL AUTO_INCREMENT,
  `action_time` datetime(6) NOT NULL,
  `object_id` longtext COLLATE utf8mb4_unicode_ci,
  `object_repr` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL,
  `action_flag` smallint unsigned NOT NULL,
  `change_message` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `content_type_id` int DEFAULT NULL,
  `user_id` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `django_admin_log_content_type_id_c4bce8eb_fk_django_co` (`content_type_id`),
  KEY `django_admin_log_user_id_c564eba6_fk_auth_user` (`user_id`),
  CONSTRAINT `django_admin_log_content_type_id_c4bce8eb_fk_django_co` FOREIGN KEY (`content_type_id`) REFERENCES `django_content_type` (`id`),
  CONSTRAINT `django_admin_log_user_id_c564eba6_fk_auth_user` FOREIGN KEY (`user_id`) REFERENCES `auth_user_management_table` (`auth_id`),
  CONSTRAINT `django_admin_log_chk_1` CHECK ((`action_flag` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `django_admin_log`
--

LOCK TABLES `django_admin_log` WRITE;
/*!40000 ALTER TABLE `django_admin_log` DISABLE KEYS */;
/*!40000 ALTER TABLE `django_admin_log` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `django_content_type`
--

DROP TABLE IF EXISTS `django_content_type`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `django_content_type` (
  `id` int NOT NULL AUTO_INCREMENT,
  `app_label` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `model` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `django_content_type_app_label_model_76bd3d3b_uniq` (`app_label`,`model`)
) ENGINE=InnoDB AUTO_INCREMENT=31 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `django_content_type`
--

LOCK TABLES `django_content_type` WRITE;
/*!40000 ALTER TABLE `django_content_type` DISABLE KEYS */;
INSERT INTO `django_content_type` VALUES (19,'admin','logentry'),(7,'assetmanagement','asset'),(8,'assetmanagement','assetdatabasetable'),(27,'assetmanagement','assetoperationlog'),(3,'assetmanagement','assettype'),(4,'assetmanagement','assettypedatabasetable'),(5,'assetmanagement','contract'),(6,'assetmanagement','contractdatabasetable'),(13,'assetmanagement','damagedasset'),(14,'assetmanagement','damagedassetdatabasetable'),(17,'assetmanagement','harddisksn'),(18,'assetmanagement','harddisksndatabasetable'),(9,'assetmanagement','outasset'),(10,'assetmanagement','outassetdatabasetable'),(11,'assetmanagement','recycleasset'),(12,'assetmanagement','recycleassetdatabasetable'),(1,'assetmanagement','storage'),(2,'assetmanagement','storagedatabasetable'),(15,'assetmanagement','wasteasset'),(16,'assetmanagement','wasteassettable'),(20,'auth','group'),(21,'auth','permission'),(26,'authusermanagement','authuser'),(22,'contenttypes','contenttype'),(23,'sessions','session'),(28,'token_blacklist','blacklistedtoken'),(29,'token_blacklist','outstandingtoken'),(30,'unregisteredasset','unregisteredasset'),(24,'usermanagement','department'),(25,'usermanagement','employee');
/*!40000 ALTER TABLE `django_content_type` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `django_migrations`
--

DROP TABLE IF EXISTS `django_migrations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `django_migrations` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `app` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `applied` datetime(6) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=47 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `django_migrations`
--

LOCK TABLES `django_migrations` WRITE;
/*!40000 ALTER TABLE `django_migrations` DISABLE KEYS */;
INSERT INTO `django_migrations` VALUES (1,'contenttypes','0001_initial','2026-05-08 15:15:06.389313'),(2,'contenttypes','0002_remove_content_type_name','2026-05-08 15:15:06.546364'),(3,'auth','0001_initial','2026-05-08 15:15:06.875353'),(4,'auth','0002_alter_permission_name_max_length','2026-05-08 15:15:06.947655'),(5,'auth','0003_alter_user_email_max_length','2026-05-08 15:15:06.954397'),(6,'auth','0004_alter_user_username_opts','2026-05-08 15:15:06.960776'),(7,'auth','0005_alter_user_last_login_null','2026-05-08 15:15:06.969495'),(8,'auth','0006_require_contenttypes_0002','2026-05-08 15:15:06.972653'),(9,'auth','0007_alter_validators_add_error_messages','2026-05-08 15:15:06.979751'),(10,'auth','0008_alter_user_username_max_length','2026-05-08 15:15:06.986633'),(11,'auth','0009_alter_user_last_name_max_length','2026-05-08 15:15:06.994499'),(12,'auth','0010_alter_group_name_max_length','2026-05-08 15:15:07.012342'),(13,'auth','0011_update_proxy_permissions','2026-05-08 15:15:07.099701'),(14,'auth','0012_alter_user_first_name_max_length','2026-05-08 15:15:07.106592'),(15,'authusermanagement','0001_initial','2026-05-08 15:15:07.538067'),(16,'admin','0001_initial','2026-05-08 15:15:07.706000'),(17,'admin','0002_logentry_remove_auto_add','2026-05-08 15:15:07.719720'),(18,'admin','0003_logentry_add_action_flag_choices','2026-05-08 15:15:07.731903'),(19,'sessions','0001_initial','2026-05-08 15:15:07.776109'),(20,'usermanagement','0001_initial','2026-05-08 15:43:06.875870'),(21,'assetmanagement','0001_initial','2026-05-08 15:43:09.710067'),(22,'usermanagement','0002_alter_department_options_alter_employee_options_and_more','2026-05-18 14:15:00.078318'),(23,'assetmanagement','0002_assetoperationlog_alter_asset_options_and_more','2026-05-18 14:15:00.819172'),(24,'authusermanagement','0002_alter_authuser_options','2026-05-18 14:15:00.826180'),(25,'token_blacklist','0001_initial','2026-05-19 08:44:36.722245'),(26,'token_blacklist','0002_outstandingtoken_jti_hex','2026-05-19 08:44:36.799876'),(27,'token_blacklist','0003_auto_20171017_2007','2026-05-19 08:44:36.826121'),(28,'token_blacklist','0004_auto_20171017_2013','2026-05-19 08:44:36.937548'),(29,'token_blacklist','0005_remove_outstandingtoken_jti','2026-05-19 08:44:37.002578'),(30,'token_blacklist','0006_auto_20171017_2113','2026-05-19 08:44:37.034458'),(31,'token_blacklist','0007_auto_20171017_2214','2026-05-19 08:44:37.272478'),(32,'token_blacklist','0008_migrate_to_bigautofield','2026-05-19 08:44:37.559413'),(33,'token_blacklist','0010_fix_migrate_to_bigautofield','2026-05-19 08:44:37.572638'),(34,'token_blacklist','0011_linearizes_history','2026-05-19 08:44:37.576421'),(35,'token_blacklist','0012_alter_outstandingtoken_user','2026-05-19 08:44:37.586165'),(36,'token_blacklist','0013_alter_blacklistedtoken_options_and_more','2026-05-19 08:44:37.599058'),(37,'usermanagement','0003_add_department_tree_fields','2026-05-19 14:28:43.608265'),(38,'assetmanagement','0003_assetoperationlog_logging_id_and_more','2026-05-24 12:09:07.130009'),(39,'assetmanagement','0004_assetoperationlog_logging_id_unique','2026-05-24 12:20:24.518061'),(40,'assetmanagement','0005_add_outasset_previous_status','2026-05-26 01:13:06.589683'),(41,'unregisteredasset','0001_initial','2026-05-26 08:57:34.717276'),(42,'assetmanagement','0006_alter_outasset_outasset_current_status','2026-06-02 08:14:18.984420'),(43,'assetmanagement','0007_alter_asset_asset_code','2026-06-05 01:52:11.415574'),(44,'assetmanagement','0008_add_recycle_record_code','2026-06-06 14:57:41.321433'),(45,'assetmanagement','0009_fill_recycle_record_code_unique','2026-06-06 14:57:41.511383'),(46,'assetmanagement','0010_remove_redundant_fields','2026-06-08 04:06:41.173139');
/*!40000 ALTER TABLE `django_migrations` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `django_session`
--

DROP TABLE IF EXISTS `django_session`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `django_session` (
  `session_key` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `session_data` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `expire_date` datetime(6) NOT NULL,
  PRIMARY KEY (`session_key`),
  KEY `django_session_expire_date_a5c62663` (`expire_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `django_session`
--

LOCK TABLES `django_session` WRITE;
/*!40000 ALTER TABLE `django_session` DISABLE KEYS */;
INSERT INTO `django_session` VALUES ('ra85wnt52efu1sd4ljdgsqzin42m2xnl','.eJxVjEEOgjAURO_StWlKC_zWnd7BdTP9fK0xEEJhZby7JWGh2_dm3ltFbGuOW5ElPgd1Vk6dflkCv2TaBea56F3sfMSEh4wyrfpYFH2p7lbd9bj8dTJKrhHyTcd3ZnIGbDx78tImCoaa3iIZDBASZ7h3NrSBOyLpAWcFtkNr1ecL8CU7CQ:1wOna8:pRIVsLbc-Jpz1sK3Eb3iqnA-6q46jFmM2XiAIZ9eyFA','2026-06-01 02:19:48.021395'),('w3wmpp1parmdj8qhkbpuet1cebjo99yu','.eJxVjEEOgjAURO_StWlKC_zWnd7BdTP9fK0xEEJhZby7JWGh2_dm3ltFbGuOW5ElPgd1Vk6dflkCv2TaBea56F3sfMSEh4wyrfpYFH2p7lbd9bj8dTJKrhHyTcd3ZnIGbDx78tImCoaa3iIZDBASZ7h3NrSBOyLpAWcFtkNr1ecL8CU7CQ:1wOna9:sv_cXbGqTcOCTXGgiPmcQdnbVFgvPVn2zd9qwUblvns','2026-06-01 02:19:49.628847');
/*!40000 ALTER TABLE `django_session` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `token_blacklist_blacklistedtoken`
--

DROP TABLE IF EXISTS `token_blacklist_blacklistedtoken`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `token_blacklist_blacklistedtoken` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `blacklisted_at` datetime(6) NOT NULL,
  `token_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `token_id` (`token_id`),
  CONSTRAINT `token_blacklist_blacklistedtoken_token_id_3cc7fe56_fk` FOREIGN KEY (`token_id`) REFERENCES `token_blacklist_outstandingtoken` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=38 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `token_blacklist_blacklistedtoken`
--

LOCK TABLES `token_blacklist_blacklistedtoken` WRITE;
/*!40000 ALTER TABLE `token_blacklist_blacklistedtoken` DISABLE KEYS */;
INSERT INTO `token_blacklist_blacklistedtoken` VALUES (1,'2026-05-19 09:25:28.339497',1),(2,'2026-05-19 12:56:20.788204',2),(4,'2026-05-20 00:22:20.994116',6),(5,'2026-05-20 08:58:08.862981',8),(6,'2026-05-20 15:01:45.576149',10),(7,'2026-05-21 12:06:18.951438',12),(8,'2026-05-22 00:39:36.065081',14),(9,'2026-05-22 06:48:54.498685',16),(10,'2026-05-22 14:38:16.009879',18),(11,'2026-05-23 01:04:29.062124',20),(12,'2026-05-23 08:24:53.424137',22),(13,'2026-05-24 13:08:31.528419',25),(14,'2026-05-25 02:18:07.498634',27),(15,'2026-05-28 08:54:37.370942',30),(17,'2026-05-31 11:29:59.985244',34),(18,'2026-06-01 00:46:22.962690',36),(19,'2026-06-01 07:56:47.981770',38),(20,'2026-06-02 00:48:52.088895',40),(21,'2026-06-02 14:26:42.643869',43),(22,'2026-06-03 01:46:31.723517',45),(23,'2026-06-03 14:12:57.434296',47),(24,'2026-06-04 02:58:42.088363',49),(26,'2026-06-06 00:52:00.137760',54),(27,'2026-06-06 15:07:41.952153',56),(29,'2026-06-07 05:47:54.451803',59),(31,'2026-06-08 12:30:50.285577',63),(32,'2026-06-08 15:12:41.851092',66),(33,'2026-06-09 06:36:22.512495',68),(34,'2026-06-10 01:13:42.436418',70),(35,'2026-06-10 08:06:20.522106',72);
/*!40000 ALTER TABLE `token_blacklist_blacklistedtoken` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `token_blacklist_outstandingtoken`
--

DROP TABLE IF EXISTS `token_blacklist_outstandingtoken`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `token_blacklist_outstandingtoken` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `token` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime(6) DEFAULT NULL,
  `expires_at` datetime(6) NOT NULL,
  `user_id` int DEFAULT NULL,
  `jti` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `token_blacklist_outstandingtoken_jti_hex_d9bdf6f7_uniq` (`jti`),
  KEY `token_blacklist_outs_user_id_83bc629a_fk_auth_user` (`user_id`),
  CONSTRAINT `token_blacklist_outs_user_id_83bc629a_fk_auth_user` FOREIGN KEY (`user_id`) REFERENCES `auth_user_management_table` (`auth_id`)
) ENGINE=InnoDB AUTO_INCREMENT=77 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `token_blacklist_outstandingtoken`
--

LOCK TABLES `token_blacklist_outstandingtoken` WRITE;
/*!40000 ALTER TABLE `token_blacklist_outstandingtoken` DISABLE KEYS */;
INSERT INTO `token_blacklist_outstandingtoken` VALUES (1,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTIyMjI3MywiaWF0IjoxNzc5MTc5MDczLCJqdGkiOiIyMzEzMGU1OTdhMjk0N2QxYTVkY2UyYzNlMDdjZThmOSIsInVzZXJfaWQiOiIzIn0.Z8RSNMRyjlOH2lIzSL6ru7taCeWVu_MnmKpqq2YtTQo','2026-05-19 09:25:28.304833','2026-05-19 20:24:33.000000',3,'23130e597a2947d1a5dce2c3e07ce8f9'),(2,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTIyNTkzOSwiaWF0IjoxNzc5MTgyNzM5LCJqdGkiOiI5MTQzZTYzNDQwNDY0ZjU4YWU5NDBjNDNkNzRiZDAwZCIsInVzZXJfaWQiOiIzIn0.DwWLpVIqY6_UWhrP4-1X_VJzgODIlXEh4c5t6Tr9MxE','2026-05-19 09:25:39.303380','2026-05-19 21:25:39.000000',3,'9143e63440464f58ae940c43d74bd00d'),(3,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTIzODU4MCwiaWF0IjoxNzc5MTk1MzgwLCJqdGkiOiIzNWQzZjllOThlMzM0YzY2OWE2Y2M3ZWExZGFhODg1MCIsInVzZXJfaWQiOiIzIn0.z1HeVI4iLQGKIIhHDipyLR6hDvZsVrMEOyHkXDuwSWU','2026-05-19 12:56:20.583519','2026-05-20 00:56:20.000000',3,'35d3f9e98e334c669a6cc7ea1daa8850'),(4,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTIzODU4MCwiaWF0IjoxNzc5MTk1MzgwLCJqdGkiOiJmOTFhYzYwOTNmODg0OGEwYmQzNWYzODZmOWQ5M2M5YiIsInVzZXJfaWQiOiIzIn0.P3Wc35Wy9wAL39GVakUBa4nxOqn4M9b-L0W9xnqIZIw','2026-05-19 12:56:20.566740','2026-05-20 00:56:20.000000',3,'f91ac6093f8848a0bd35f386f9d93c9b'),(5,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTIzODU4MCwiaWF0IjoxNzc5MTk1MzgwLCJqdGkiOiJlODg0NDhiMDBlMzQ0MjE1YWVhZmUzNDIxMmE0ODljZCIsInVzZXJfaWQiOiIzIn0.27D2qBBs06SDfBsueD4IZC4j4CnCK5ASZnjMvuCsTmY','2026-05-19 12:56:20.563116','2026-05-20 00:56:20.000000',3,'e88448b00e344215aeafe34212a489cd'),(6,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTI0NzE0NSwiaWF0IjoxNzc5MjAzOTQ1LCJqdGkiOiI5NWE3NzA0YzM4YTA0YjBhODNhZTI1YzkyMWZlMDgwMCIsInVzZXJfaWQiOiIzIn0.CBBNQ8XUgGKqdV9xA2lkt2xITj0O0XV9vzd49JLBHrY','2026-05-19 15:19:05.175926','2026-05-20 03:19:05.000000',3,'95a7704c38a04b0a83ae25c921fe0800'),(7,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTI3OTc0MCwiaWF0IjoxNzc5MjM2NTQwLCJqdGkiOiI5MjI3ZDU0NGM3MjI0OTM0OGU3YjI3ZDVjOWMyODEwNiIsInVzZXJfaWQiOiIzIn0.aMXVjczyOBB6fkmz90fbRFHvpJRnzBWFdOYDA967PNE','2026-05-20 00:22:20.909089','2026-05-20 12:22:20.000000',3,'9227d544c72249348e7b27d5c9c28106'),(8,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTI4ODE0MiwiaWF0IjoxNzc5MjQ0OTQyLCJqdGkiOiJkNjE0NmNiOWI3Njg0M2FkODIyOWM3ZGI2OTE3YjBhNyIsInVzZXJfaWQiOiIzIn0.eOser7t9Xv1SSLPyVcGDZ4xxWaZSEdx7GAoBxRfs2Wo','2026-05-20 02:42:22.182508','2026-05-20 14:42:22.000000',3,'d6146cb9b76843ad8229c7db6917b0a7'),(9,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTMxMDY4OCwiaWF0IjoxNzc5MjY3NDg4LCJqdGkiOiJjZTdmMzBjNjI3YTc0ZDMwYTUxYWYxOTRlMTNiODZmMyIsInVzZXJfaWQiOiIzIn0.mcDlq7O9R0MMxy6ltP3NjngEFy5UF82S4kvfT6KF2So','2026-05-20 08:58:08.847110','2026-05-20 20:58:08.000000',3,'ce7f30c627a74d30a51af194e13b86f3'),(10,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTMyNTI1NiwiaWF0IjoxNzc5MjgyMDU2LCJqdGkiOiJmOWE0ZmViNmM0Y2I0Y2JiYmQzNTc3YjRmODJhZmRkOSIsInVzZXJfaWQiOiIzIn0.1QWeCFE_jQrKgHHKUto1VoCdaFts-V6FVMPK6_l_rOA','2026-05-20 13:00:56.142772','2026-05-21 01:00:56.000000',3,'f9a4feb6c4cb4cbbbd3577b4f82afdd9'),(11,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTMzMjUwNSwiaWF0IjoxNzc5Mjg5MzA1LCJqdGkiOiJlMWFiZjUzMGIwZTQ0MDkyOGYwZDU4MTVjMWQ1YzcxMSIsInVzZXJfaWQiOiIzIn0.JLpAGARBmnCz3b8m-nGYJl2PCUim0NtqxxlcWhDuugE','2026-05-20 15:01:45.550148','2026-05-21 03:01:45.000000',3,'e1abf530b0e440928f0d5815c1d5c711'),(12,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTM5OTkzOCwiaWF0IjoxNzc5MzU2NzM4LCJqdGkiOiI3NGJiNDZlM2JmZTc0Zjk0YjVhMmEzYTUzNmVlZDc4YSIsInVzZXJfaWQiOiIzIn0.j2DnvKeFHrQFu9qLhaV4sFQoPvhLGEXkNe91R-Am0PY','2026-05-21 09:45:38.619935','2026-05-21 21:45:38.000000',3,'74bb46e3bfe74f94b5a2a3a536eed78a'),(13,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTQwODM3OCwiaWF0IjoxNzc5MzY1MTc4LCJqdGkiOiJkMTI1YzY2NTI5Mjk0M2JmYmFkNzZmNmFiNDJmYWE4OCIsInVzZXJfaWQiOiIzIn0.rHY4ogpacHiuYiZBRt38UHL3gmxe5068emHIfMgQmfo','2026-05-21 12:06:18.904251','2026-05-22 00:06:18.000000',3,'d125c665292943bfbad76f6ab42faa88'),(14,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTQxNTg0MiwiaWF0IjoxNzc5MzcyNjQyLCJqdGkiOiI4MjI4MjJlZjllZTA0ZWZkYjBlZTgzNzA5MDM2ZjM4MSIsInVzZXJfaWQiOiIzIn0.i7dtKdj2lVHHqZCr7MQUt90TbO0BbSqQlRoyceEBjJQ','2026-05-21 14:10:42.256028','2026-05-22 02:10:42.000000',3,'822822ef9ee04efdb0ee83709036f381'),(15,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTQ1MzU3NiwiaWF0IjoxNzc5NDEwMzc2LCJqdGkiOiI5N2M0MTEzN2JiODA0Y2YxYTFiYWNkN2NkZTg2ZTRhZCIsInVzZXJfaWQiOiIzIn0.-JsnYuaU_1Eo0fuCly9i9veNqTCymrvpULQw16nqyrg','2026-05-22 00:39:36.012853','2026-05-22 12:39:36.000000',3,'97c41137bb804cf1a1bacd7cde86e4ad'),(16,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTQ2MTAxNCwiaWF0IjoxNzc5NDE3ODE0LCJqdGkiOiIxZDE5MDhjNTBlMDU0OWQ0OTc4ZDE0MDQ0MWI1YTEwNCIsInVzZXJfaWQiOiIzIn0.EJJLlABzzj41UdZpKw2RrgQBzlNc23FePQub8oa55Sc','2026-05-22 02:43:34.538487','2026-05-22 14:43:34.000000',3,'1d1908c50e0549d4978d140441b5a104'),(17,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTQ3NTczNCwiaWF0IjoxNzc5NDMyNTM0LCJqdGkiOiI2NDM5YTZmMzQ3ZTM0YmI2OTlhMDY4N2Y1ZGVjNDgxMiIsInVzZXJfaWQiOiIzIn0.gJUTSNmwy9eTyDejY7Er3dTF0Iuf07VxxikRuGgLFOY','2026-05-22 06:48:54.462284','2026-05-22 18:48:54.000000',3,'6439a6f347e34bb699a0687f5dec4812'),(18,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTQ4MzA1NiwiaWF0IjoxNzc5NDM5ODU2LCJqdGkiOiI2Nzk2NzkyZmJlYjA0YzRjYWNmODU3NWE1ZDNmMzJjZiIsInVzZXJfaWQiOiIzIn0.yo9IhmHekgfXtAVjC5OC8ArWP8Gvc8MieDocQPsjwFE','2026-05-22 08:50:56.385151','2026-05-22 20:50:56.000000',3,'6796792fbeb04c4cacf8575a5d3f32cf'),(19,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTUwMzg5NSwiaWF0IjoxNzc5NDYwNjk1LCJqdGkiOiJiOWUyZmIwZDlhNzY0MDgzOGRlMGFkNTIzYTViNGVmNiIsInVzZXJfaWQiOiIzIn0.70IuVd-px6wuM4852gB6QZ5DSw-3Zbo8ZKmfy-e71hs','2026-05-22 14:38:15.974427','2026-05-23 02:38:15.000000',3,'b9e2fb0d9a7640838de0ad523a5b4ef6'),(20,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTUxMjg0NCwiaWF0IjoxNzc5NDY5NjQ0LCJqdGkiOiI5MmVlZWQ3ZjEyN2E0ODU1YmJjMTdkNjNjNjcwZmFmNiIsInVzZXJfaWQiOiIzIn0.e-QoITcxNgtVmPmHkFtQKacDSI501Rbhg1LihLwgI2Q','2026-05-22 17:07:24.383021','2026-05-23 05:07:24.000000',3,'92eeed7f127a4855bbc17d63c670faf6'),(21,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTU0MTQ2OSwiaWF0IjoxNzc5NDk4MjY5LCJqdGkiOiI5YjZkNjNhZjMwODg0YzUxOTUwMjYwNmE0OTRkMTA1MCIsInVzZXJfaWQiOiIzIn0.PfLFV982OXOVxWfauYedQmwpl2mCepMHhwm5wAOG4Kw','2026-05-23 01:04:29.040411','2026-05-23 13:04:29.000000',3,'9b6d63af30884c519502606a494d1050'),(22,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTU2MDY4MywiaWF0IjoxNzc5NTE3NDgzLCJqdGkiOiJjNDcxZDEzY2I5NGY0ZDdmYTNmODU5MGUyYzBlYWJjMCIsInVzZXJfaWQiOiIzIn0._lSZC1am_H6m7wFMJ40rEPUYChHsHXSxKy6e8899aL0','2026-05-23 06:24:43.640766','2026-05-23 18:24:43.000000',3,'c471d13cb94f4d7fa3f8590e2c0eabc0'),(23,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTU2Nzg5MywiaWF0IjoxNzc5NTI0NjkzLCJqdGkiOiJiZjk1ZDNlZGEzMjA0N2ZmYmZlNTgzOGU0ZWRiMzkxZSIsInVzZXJfaWQiOiIzIn0.UgGjlp4dRuTDjmsBmlBKQ6KpOa33hLEW4QBRkhmhqOQ','2026-05-23 08:24:53.413382','2026-05-23 20:24:53.000000',3,'bf95d3eda32047ffbfe5838e4edb391e'),(24,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTU5MDgyOCwiaWF0IjoxNzc5NTQ3NjI4LCJqdGkiOiI4YTMwZWMzNTA0MGM0OWRhYWY0MWFhYzc3MDA2MDExYSIsInVzZXJfaWQiOiIzIn0.-ZjOS1to01WHuMq0tpvB8XnfLT6_kVK_L6vK8wPBmzA','2026-05-23 14:47:08.562286','2026-05-24 02:47:08.000000',3,'8a30ec35040c49daaf41aac77006011a'),(25,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTY2NDEwMywiaWF0IjoxNzc5NjIwOTAzLCJqdGkiOiIxMWZkMjM3ODhkMTI0N2UzYjdiNGU4Zjc3MWMyYzkwNCIsInVzZXJfaWQiOiIzIn0.goASFBAU--vC-lzNZm1YQHTqJx5oXSQtAdaTgJK2ZYE','2026-05-24 11:08:23.244522','2026-05-24 23:08:23.000000',3,'11fd23788d1247e3b7b4e8f771c2c904'),(26,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTY3MTMxMSwiaWF0IjoxNzc5NjI4MTExLCJqdGkiOiJlNWU2MjFjNzlmNmQ0NjYyYmIxMTMzMjEwZDVmNWM0ZiIsInVzZXJfaWQiOiIzIn0.JAdGMYcOfe9XhuKNqnHkjfEuv9pVGtQt5PVX4kaDR58','2026-05-24 13:08:31.498426','2026-05-25 01:08:31.000000',3,'e5e621c79f6d4662bb1133210d5f5c4f'),(27,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTY3ODg5NCwiaWF0IjoxNzc5NjM1Njk0LCJqdGkiOiJiMzU0NDFhYmFiMzA0ZjEyYTZjYTAzMmYzNzNmNjY2MiIsInVzZXJfaWQiOiIzIn0.uI5_-fe5-JlREb0nf4U6hmV07_aRBFvSBdCG7JMlscw','2026-05-24 15:14:54.508558','2026-05-25 03:14:54.000000',3,'b35441abab304f12a6ca032f373f6662'),(28,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTcxODY4NywiaWF0IjoxNzc5Njc1NDg3LCJqdGkiOiJhNzBiMTlkNTRkMWY0ZGU1ODc0MzJmNDFiNGFiMWM3MyIsInVzZXJfaWQiOiIzIn0.VJcXCgKBKouRhx1CA6dW5WSZNjbmBFVHJ2xpPfCBEks','2026-05-25 02:18:07.459507','2026-05-25 14:18:07.000000',3,'a70b19d54d1f4de587432f41b4ab1c73'),(29,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTc2MTMwOCwiaWF0IjoxNzc5NzE4MTA4LCJqdGkiOiI5MzRiMjEyZjI3OTk0MWRmOTNkNTJkNjUzMTExZjg0YSIsInVzZXJfaWQiOiIzIn0.Z4zneQu8SQnEbyW1V1Zwv_gEAwDyAULbHADeC6VUkAQ','2026-05-25 14:08:28.385036','2026-05-26 02:08:28.000000',3,'934b212f279941df93d52d653111f84a'),(30,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc3OTk4Mzc1MCwiaWF0IjoxNzc5OTQwNTUwLCJqdGkiOiI0MGIzOTE1ODA5YWQ0ODhiYWQ0NGRmM2U3NTQyMzlkMiIsInVzZXJfaWQiOiIzIn0.e1V6NwHcrln-Y8lRG-XyAbAcKvaQFzhTLPUD149U3g4','2026-05-28 03:55:50.419771','2026-05-28 15:55:50.000000',3,'40b3915809ad488bad44df3e754239d2'),(31,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDAwMTY3NywiaWF0IjoxNzc5OTU4NDc3LCJqdGkiOiI1ZGQ1YzA4MmIzMGI0YTVlOTg4YmMwN2MwY2MxMjBhMCIsInVzZXJfaWQiOiIzIn0.K0AoxnWZaQa85F-O1mKc8EenOCH_wSDPylRBL4jdo3U','2026-05-28 08:54:37.350319','2026-05-28 20:54:37.000000',3,'5dd5c082b30b4a5e988bc07c0cc120a0'),(32,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDAwMTY3NywiaWF0IjoxNzc5OTU4NDc3LCJqdGkiOiIxOTZjMjBlYjRjZGE0MDFmOTM5NTRjN2ZlNTNkYWUwNiIsInVzZXJfaWQiOiIzIn0.f-6Spd1I96F2JQnDGkkxAvRGO8q1XXDwDgjnyFQwzDI','2026-05-28 08:54:37.353055','2026-05-28 20:54:37.000000',3,'196c20eb4cda401f93954c7fe53dae06'),(33,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDA2MzA4OSwiaWF0IjoxNzgwMDE5ODg5LCJqdGkiOiIxNzUwMWQyN2QyMmQ0M2I0YTk3ZDNlMGMxYWRhZjM5ZSIsInVzZXJfaWQiOiIzIn0.vogYdPNkUTUZNrFwTTVrKAjaMHLSBgMpyUqAYJOUVYw','2026-05-29 01:58:09.699080','2026-05-29 13:58:09.000000',3,'17501d27d22d43b4a97d3e0c1adaf39e'),(34,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDI2MDUzMywiaWF0IjoxNzgwMjE3MzMzLCJqdGkiOiJkMWU4M2Y3N2JjMjI0MWI0YjUxNzUyMmIyY2ZkZWVhMiIsInVzZXJfaWQiOiIzIn0.zasg92r4VKSgX7lWyUu0_ikNtBLYuQ-5iWCi5ZNQDjk','2026-05-31 08:48:53.171211','2026-05-31 20:48:53.000000',3,'d1e83f77bc2241b4b517522b2cfdeea2'),(35,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDI3MDE5OSwiaWF0IjoxNzgwMjI2OTk5LCJqdGkiOiI4MWZiYzliM2ZjYzE0NWIwYjU1ZDY3NGFiNTliZTNlMCIsInVzZXJfaWQiOiIzIn0.Bm07R555cxpaxxqRfqD9wtpDGWxTqdcA6LsCI00vJsU','2026-05-31 11:29:59.944493','2026-05-31 23:29:59.000000',3,'81fbc9b3fcc145b0b55d674ab59be3e0'),(36,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDI4MjA2NiwiaWF0IjoxNzgwMjM4ODY2LCJqdGkiOiIwNTM4Y2IyZTkwN2Q0NzM5OTNmNDE3ZWRjNDFmM2U5NSIsInVzZXJfaWQiOiIzIn0.ZK4nb7wu4pfhjDDLutAxfVEV82sYXjLd5Uth-m4EqP0','2026-05-31 14:47:46.946982','2026-06-01 02:47:46.000000',3,'0538cb2e907d473993f417edc41f3e95'),(37,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDMxNzk4MiwiaWF0IjoxNzgwMjc0NzgyLCJqdGkiOiJhMDE0NTc1Mzg5NzU0MmViYjVmMzVjYmQ1YmQ2YTM5YSIsInVzZXJfaWQiOiIzIn0.mNvw3bK_OkevVUzgSHlMvR6TokU9QTYIRWpHxMlSZus','2026-06-01 00:46:22.862112','2026-06-01 12:46:22.000000',3,'a0145753897542ebb5f35cbd5bd6a39a'),(38,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDMyNTMzMiwiaWF0IjoxNzgwMjgyMTMyLCJqdGkiOiJlZGRiYWJiZmNiNzA0ODQyOWVmYjViNTc4ZDY5YjdhNyIsInVzZXJfaWQiOiIzIn0.TrmFtw8MccoszlmMi-0kvSSHBvme6JeRlFJU--s_qqc','2026-06-01 02:48:52.285850','2026-06-01 14:48:52.000000',3,'eddbabbfcb7048429efb5b578d69b7a7'),(39,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDM0MzgwNywiaWF0IjoxNzgwMzAwNjA3LCJqdGkiOiI2MThjMTk0YWU0MGI0MDlhODNlOWFhZjA0Y2IxY2JmZCIsInVzZXJfaWQiOiIzIn0.11CekQanhw1RHbxkG0_G1qlHjJ17Qz98AGX_zl-aAYM','2026-06-01 07:56:47.936367','2026-06-01 19:56:47.000000',3,'618c194ae40b409a83e9aaf04cb1cbfd'),(40,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDM3MDA3NSwiaWF0IjoxNzgwMzI2ODc1LCJqdGkiOiJlNWQ1ODhjNjg0NDQ0ZWU0OWJiMDhjOGYxNjZhODNkOCIsInVzZXJfaWQiOiIzIn0.QAQQynqpqxv7uF-40WhPoNFbvamyvQydeSnvyR14psc','2026-06-01 15:14:35.876768','2026-06-02 03:14:35.000000',3,'e5d588c684444ee49bb08c8f166a83d8'),(41,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDQwNDUzMiwiaWF0IjoxNzgwMzYxMzMyLCJqdGkiOiI0YTY4ZDY4MTJkYTM0MDM3OGY0OTc2NDI4NjkyNTUwYSIsInVzZXJfaWQiOiIzIn0.VGyVkaSn772QdWWPen2F2O0OvPGZMtRMyZIhW8MsqvU','2026-06-02 00:48:52.022970','2026-06-02 12:48:52.000000',3,'4a68d6812da340378f4976428692550a'),(42,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDQwNzQ3NiwiaWF0IjoxNzgwMzY0Mjc2LCJqdGkiOiI1MTI1ZTRiOWY4MDM0MDM2OWVlYmNkM2FlOTYwZmE0MyIsInVzZXJfaWQiOiIzIn0.jeuz7wBOKLotU425vp6grLOA73-bOY8k3vhmAv1shEo','2026-06-02 01:37:56.650228','2026-06-02 13:37:56.000000',3,'5125e4b9f80340369eebcd3ae960fa43'),(43,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDQzNTMyMCwiaWF0IjoxNzgwMzkyMTIwLCJqdGkiOiI1ZWNkOTMyODAyOGI0MGY5YmIwY2NiN2EwY2E5OTliMSIsInVzZXJfaWQiOiIzIn0.v9eUfsNcksZmZpIs6XIKGEbNmt_DngZsFyPbOuaDyMQ','2026-06-02 09:22:00.585187','2026-06-02 21:22:00.000000',3,'5ecd9328028b40f9bb0ccb7a0ca999b1'),(44,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDQ1MzYwMiwiaWF0IjoxNzgwNDEwNDAyLCJqdGkiOiI4OGYwMmY5ODczZjE0MDgzYTc3NTYwNTAxZTZhZjFmYSIsInVzZXJfaWQiOiIzIn0.08nt-Wh_QpbVs1OA8ikuV9LzMOn731B7hgphdVx7q88','2026-06-02 14:26:42.586642','2026-06-03 02:26:42.000000',3,'88f02f9873f14083a77560501e6af1fa'),(45,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDQ2MDk3MSwiaWF0IjoxNzgwNDE3NzcxLCJqdGkiOiIzNWY4MDNkZTc3OWM0ZDNiOWU1NDhlYWM2ZDYxYjA2YiIsInVzZXJfaWQiOiIzIn0.jYhUUTQm3SRZYH4G4lfQIxSNymdL4MuzlQT0i3WE6oo','2026-06-02 16:29:31.416260','2026-06-03 04:29:31.000000',3,'35f803de779c4d3b9e548eac6d61b06b'),(46,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDQ5NDM5MSwiaWF0IjoxNzgwNDUxMTkxLCJqdGkiOiI5OTJkZjIwNzAxNjA0ZTQyYWYxNzBjNTM5YzNmNWUwZSIsInVzZXJfaWQiOiIzIn0.OcPVepubRFwFPRddFVyzM_5wRUCVvgPxJNsEekqf6cg','2026-06-03 01:46:31.648337','2026-06-03 13:46:31.000000',3,'992df20701604e42af170c539c3f5e0e'),(47,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDUzMDcxNiwiaWF0IjoxNzgwNDg3NTE2LCJqdGkiOiI0NTgyMzI0OWY2ZGI0YmJjYmIyYTJhZDY2NzU4MDVjOSIsInVzZXJfaWQiOiIzIn0.ZIVmuXnMM6WgLC4YO2RWv5Lq69NJwF4RwXbHVuvmGvg','2026-06-03 11:51:56.796239','2026-06-03 23:51:56.000000',3,'45823249f6db4bbcbb2a2ad6675805c9'),(48,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDUzOTE3NywiaWF0IjoxNzgwNDk1OTc3LCJqdGkiOiI4NjBlZmViYWQ0MWI0M2RkOGEzZDQ4NzZlNDc4YjNjZSIsInVzZXJfaWQiOiIzIn0.kGSwE6D2BpGkpQYshIMvCBj4WzXVodtSj6x5VSFdvIE','2026-06-03 14:12:57.411891','2026-06-04 02:12:57.000000',3,'860efebad41b43dd8a3d4876e478b3ce'),(49,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDU3NzA4OSwiaWF0IjoxNzgwNTMzODg5LCJqdGkiOiJlMjZlYTc3ODk1MzY0Y2YyOTg0ZTI4YTMxYzRhNGQ0YiIsInVzZXJfaWQiOiIzIn0.XBGv1tJqzTjfs7tvHi1aQ7uAqCeCwLlY5P8ZjtHK0gk','2026-06-04 00:44:49.167061','2026-06-04 12:44:49.000000',3,'e26ea77895364cf2984e28a31c4a4d4b'),(50,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDU4NTEyMiwiaWF0IjoxNzgwNTQxOTIyLCJqdGkiOiI5M2RmMmE0YWQ2NzA0OWNmOTdiZjY5YzA3MDczMzc2YSIsInVzZXJfaWQiOiIzIn0.iCNtoRTt03XCrEhGarFRAWUv4lZ-VSyO_Ly4GJpd7Ew','2026-06-04 02:58:42.045573','2026-06-04 14:58:42.000000',3,'93df2a4ad67049cf97bf69c07073376a'),(51,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDU4NTEyMiwiaWF0IjoxNzgwNTQxOTIyLCJqdGkiOiI2NzA1NGI5N2I3YjI0MmNiOGVmY2ExMDNjMWIwZTg0ZSIsInVzZXJfaWQiOiIzIn0.9lx2p8ont7-8fLXQH9PkuBqsgDAnofpT1njvAsLGkzU','2026-06-04 02:58:42.052595','2026-06-04 14:58:42.000000',3,'67054b97b7b242cb8efca103c1b0e84e'),(52,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDYyMjU4OCwiaWF0IjoxNzgwNTc5Mzg4LCJqdGkiOiJiOWFlODBhNWU1ZTI0NjA4OTExNTlhMjM0OGRkOTc3NiIsInVzZXJfaWQiOiIzIn0.pPS9Yu-o4I6a96jvsFl9CBB7gHKMtFg0BRobdGB5Q1w','2026-06-04 13:23:08.419543','2026-06-05 01:23:08.000000',3,'b9ae80a5e5e2460891159a2348dd9776'),(53,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDY2ODE1OSwiaWF0IjoxNzgwNjI0OTU5LCJqdGkiOiJhYzk5NmFiZDNkOWE0YjdlOWU4NTViN2NiMjJlOGE0YSIsInVzZXJfaWQiOiIzIn0.kaEpcCqjt9Pq4TJ_xkedSZ-u3bXgsmvKwptZ4DQlql4','2026-06-05 02:02:39.433679','2026-06-05 14:02:39.000000',3,'ac996abd3d9a4b7e9e855b7cb22e8a4a'),(54,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDcxNDg0MywiaWF0IjoxNzgwNjcxNjQzLCJqdGkiOiI4MTBjNTM1NzdkNzk0Y2JkYjQ3ZWY3YmQyOWE4MDJkNiIsInVzZXJfaWQiOiIzIn0.EJPHkZdlhO1dZ-sRbUN7IkjzlaTWnZh1xP7foMeZRj4','2026-06-05 15:00:43.171226','2026-06-06 03:00:43.000000',3,'810c53577d794cbdb47ef7bd29a802d6'),(55,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDc1MDMyMCwiaWF0IjoxNzgwNzA3MTIwLCJqdGkiOiJmMjNkZTUyMjk3NzQ0NjQ3OWY0ZjMwNWE4Mjg5NGZiNSIsInVzZXJfaWQiOiIzIn0.bGSBhGctHLc7MHbL98X8BYEv0t48MVaNiAqBwaAQR1w','2026-06-06 00:52:00.097966','2026-06-06 12:52:00.000000',3,'f23de522977446479f4f305a82894fb5'),(56,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDc5MTQ3NCwiaWF0IjoxNzgwNzQ4Mjc0LCJqdGkiOiI2ZTlkZjczNzc5ZWE0NmFjYTU1ZjFmODAwY2MyOGVlMiIsInVzZXJfaWQiOiIzIn0.WuitZ9JNMSsmKXFJNsJPAST0TsGmoMXzN91GwHy4myk','2026-06-06 12:17:54.365319','2026-06-07 00:17:54.000000',3,'6e9df73779ea46aca55f1f800cc28ee2'),(57,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDgwMTY2MSwiaWF0IjoxNzgwNzU4NDYxLCJqdGkiOiI3YTg2NzdiODAwMmQ0ZDIwYjk2NTFjNjE1NGFhOTQ1MSIsInVzZXJfaWQiOiIzIn0.zEFS_jYoet6GujGJze0tww22CL2r671WEMxJs0IFxGc','2026-06-06 15:07:41.935069','2026-06-07 03:07:41.000000',3,'7a8677b8002d4d20b9651c6154aa9451'),(58,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDgwMTY2MSwiaWF0IjoxNzgwNzU4NDYxLCJqdGkiOiI4ZmU3OGJmMThiOWY0MWJkYjhhMDI2MDlhMzA1Yzc1NiIsInVzZXJfaWQiOiIzIn0.yGdaITpMYSry4kzYNOLyzCT6UN7bnczMDz586mUqi-E','2026-06-06 15:07:41.933168','2026-06-07 03:07:41.000000',3,'8fe78bf18b9f41bdb8a02609a305c756'),(59,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDgzNTA0MSwiaWF0IjoxNzgwNzkxODQxLCJqdGkiOiI5ZjNjOGYzYWZjYTU0MjVmODU4Yzk4NzQxYTBiODg0MyIsInVzZXJfaWQiOiIzIn0.6XidE4aiLD64sTMJTHVE9x-5r_m3QcTUmBNx6zteDIk','2026-06-07 00:24:01.447522','2026-06-07 12:24:01.000000',3,'9f3c8f3afca5425f858c98741a0b8843'),(60,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDg1NDQ3NCwiaWF0IjoxNzgwODExMjc0LCJqdGkiOiI4Mjk3YjcwYjExYTY0Y2IzOTBjYTgwMWNiNDg1ODVhNSIsInVzZXJfaWQiOiIzIn0.ySMWmVc5RrCNfJYSk4GPRfY14AhcsnyaQXzCsTPaLP8','2026-06-07 05:47:54.404284','2026-06-07 17:47:54.000000',3,'8297b70b11a64cb390ca801cb48585a5'),(61,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDg1NDQ3NCwiaWF0IjoxNzgwODExMjc0LCJqdGkiOiIwNzRkZGUwZmI1MmI0NDNhYWNlNjNjYjIyNzcwYmQ2YSIsInVzZXJfaWQiOiIzIn0.qHtlz1eT4MXJQbU9MtQi1ui7HkD5CaTeTT2UOC8XlEg','2026-06-07 05:47:54.402116','2026-06-07 17:47:54.000000',3,'074dde0fb52b443aace63cb22770bd6a'),(62,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDg3NzM1NiwiaWF0IjoxNzgwODM0MTU2LCJqdGkiOiI1YjljODlkNzBiYjg0MDIzYjdiZmEzOTUxN2Y3NzdlNyIsInVzZXJfaWQiOiIzIn0.AwT0A76GrgTemLQJmShG8agHDmGXrXj_LUNAJlgaYYM','2026-06-07 12:09:16.449813','2026-06-08 00:09:16.000000',3,'5b9c89d70bb84023b7bfa39517f777e7'),(63,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDk0NjAyMiwiaWF0IjoxNzgwOTAyODIyLCJqdGkiOiI5NTVhZTQ1YjAxYjE0MmE3OGIzMzRmYWZlOWQxZjIyMiIsInVzZXJfaWQiOiIzIn0.HlQZHC_K1EqPq30vwjQ-77VEb8n2Dl7ouP796Zb8ypY','2026-06-08 07:13:42.485704','2026-06-08 19:13:42.000000',3,'955ae45b01b142a78b334fafe9d1f222'),(64,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDk2NTA1MCwiaWF0IjoxNzgwOTIxODUwLCJqdGkiOiI2MjE1M2FlOTcyMGI0NjUyOWFmMjNjOWI1OWYyYWQxOCIsInVzZXJfaWQiOiIzIn0.V8866206q2f4sgfLdUlmn-ek10gJiYu0kxGifd-HBHA','2026-06-08 12:30:50.266947','2026-06-09 00:30:50.000000',3,'62153ae9720b46529af23c9b59f2ad18'),(65,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDk2NTA1MCwiaWF0IjoxNzgwOTIxODUwLCJqdGkiOiIyNDg1MThiOWU4NzA0Y2E0OWQxZmM3YjVkYjVkOTgwNCIsInVzZXJfaWQiOiIzIn0.svEoQo0Z0C6TG3GrJgoQf1bpwg_KWSSlp2DOF9B5wf8','2026-06-08 12:30:50.275515','2026-06-09 00:30:50.000000',3,'248518b9e8704ca49d1fc7b5db5d9804'),(66,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDk2NTI3MiwiaWF0IjoxNzgwOTIyMDcyLCJqdGkiOiIyMzM0MDQyMjcwNWE0ZDA5OTU5YTM4N2JiNzBmMDc5MyIsInVzZXJfaWQiOiIzIn0.p-qomsG730RtGqfw5SrNwNZZLRpcbGjh-F9qegRSYDc','2026-06-08 12:34:32.276388','2026-06-09 00:34:32.000000',3,'23340422705a4d09959a387bb70f0793'),(67,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MDk3NDc2MSwiaWF0IjoxNzgwOTMxNTYxLCJqdGkiOiJkYTU2Mjk0MjVhYjc0OTdlYWNlYjRlZTQ2ZWViZDIzMyIsInVzZXJfaWQiOiIzIn0.OGpRHTa2zwJRt5WIKLicivF5E-btfYxiCAaDAO4HXEE','2026-06-08 15:12:41.757275','2026-06-09 03:12:41.000000',3,'da5629425ab7497eaceb4ee46eebd233'),(68,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MTAxMjI0MiwiaWF0IjoxNzgwOTY5MDQyLCJqdGkiOiIyZmNjMjNhMDBiNzM0MmE1ODdhYTY3ZDY0NzA1Njg1YiIsInVzZXJfaWQiOiIzIn0.UPWJk1Okp0OQL8gSjcGQXEdjkxOCvQrRs3wG3FEVz1o','2026-06-09 01:37:22.864472','2026-06-09 13:37:22.000000',3,'2fcc23a00b7342a587aa67d64705685b'),(69,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MTAzMDE4MiwiaWF0IjoxNzgwOTg2OTgyLCJqdGkiOiJiOTRkYzVjNTljYTg0YTU5YTFjOWUzNjY4MTEwODc4OSIsInVzZXJfaWQiOiIzIn0.uHtHKACI7XE2FsnkYgyiIC6NUJWBtK_73bfMjD3foLk','2026-06-09 06:36:22.495098','2026-06-09 18:36:22.000000',3,'b94dc5c59ca84a59a1c9e36681108789'),(70,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MTA1NzczNCwiaWF0IjoxNzgxMDE0NTM0LCJqdGkiOiIwYzMzZmJmNDVmZjE0NjRjOTg3NjczZjhmZjA5OGJhZCIsInVzZXJfaWQiOiIzIn0.pAa7euBEyxHANr4CrsdnRBXJjTKzmcqReKDFZUZaj7k','2026-06-09 14:15:34.122503','2026-06-10 02:15:34.000000',3,'0c33fbf45ff1464c987673f8ff098bad'),(71,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MTA5NzIyMiwiaWF0IjoxNzgxMDU0MDIyLCJqdGkiOiI5MGZmNjI4ZmZkYjY0MzdiYWNhOTAyYjkxNDY0YmNmZSIsInVzZXJfaWQiOiIzIn0.uM7bQ67DwDtIASFd7eR04g3jagh3c4oJSMoZvEBO4Mc','2026-06-10 01:13:42.401056','2026-06-10 13:13:42.000000',3,'90ff628ffdb6437baca902b91464bcfe'),(72,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MTEwNTMwOSwiaWF0IjoxNzgxMDYyMTA5LCJqdGkiOiJiZDU4ZmZjOTMzMjI0OWM2YjlmNjJkN2Q5NjU3ZjM0MSIsInVzZXJfaWQiOiIzIn0.-oQKugfarpwofD9FuXCXFMrRUx68sJ65TW9q15I2KsI','2026-06-10 03:28:29.532553','2026-06-10 15:28:29.000000',3,'bd58ffc9332249c6b9f62d7d9657f341'),(73,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MTEyMTk4MCwiaWF0IjoxNzgxMDc4NzgwLCJqdGkiOiI2Y2ZlYjYyYzk0MzI0MmY4OGIzZDNhMzUxMDkwNjE5NCIsInVzZXJfaWQiOiIzIn0.4V3cyNRxxYoqwUPaseA09YSgfosZuiZ2mqEX9q2PGTE','2026-06-10 08:06:20.384389','2026-06-10 20:06:20.000000',3,'6cfeb62c943242f88b3d3a3510906194'),(74,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MTEyMTk4MCwiaWF0IjoxNzgxMDc4NzgwLCJqdGkiOiI2MzczZTBkMzkzZTE0MTFjYjA5ZjRkNzljYTQ0YWMzMCIsInVzZXJfaWQiOiIzIn0.2iPv8DLoCY50CSKV014VOCwxEadub_k4qYk5QhYftQY','2026-06-10 08:06:20.391497','2026-06-10 20:06:20.000000',3,'6373e0d393e1411cb09f4d79ca44ac30'),(75,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MTEyMTk4MCwiaWF0IjoxNzgxMDc4NzgwLCJqdGkiOiJhMjUzOTdlNWI2YjU0ZjJiYWRkMWFjOTBiN2JjMWVjZiIsInVzZXJfaWQiOiIzIn0.5glb6MxQP3I0Q_0se8kOsamGqA7un3sWVMFckM_CnGI','2026-06-10 08:06:20.402350','2026-06-10 20:06:20.000000',3,'a25397e5b6b54f2badd1ac90b7bc1ecf'),(76,'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTc4MTEzMzYyOSwiaWF0IjoxNzgxMDkwNDI5LCJqdGkiOiJiNmZmYmNlODFkOTk0ZWZiYjA2ODg0MTUyODFjYmM0MCIsInVzZXJfaWQiOiIzIn0.LxQu7zVnDuhiJ-U0G4iBmBBSFp0vpIQ1IZzdVNDX5b4','2026-06-10 11:20:29.845093','2026-06-10 23:20:29.000000',3,'b6ffbce81d994efbb0688415281cbc40');
/*!40000 ALTER TABLE `token_blacklist_outstandingtoken` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `user_database_table`
--

DROP TABLE IF EXISTS `user_database_table`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_database_table` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `employee_jobcode` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `employee_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `employee_status` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL,
  `employee_phone` varchar(15) COLLATE utf8mb4_unicode_ci NOT NULL,
  `employee_location` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `employee_description` longtext COLLATE utf8mb4_unicode_ci,
  `employee_department_id` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `sort_order` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `employee_jobcode` (`employee_jobcode`),
  UNIQUE KEY `employee_phone` (`employee_phone`),
  KEY `user_database_table_employee_department__ebe8d0c8_fk_departmen` (`employee_department_id`),
  KEY `user_databa_employe_6dfa3c_idx` (`employee_jobcode`),
  KEY `user_databa_employe_1dc263_idx` (`employee_name`),
  KEY `user_databa_sort_or_131b07_idx` (`sort_order`),
  CONSTRAINT `user_database_table_employee_department__ebe8d0c8_fk_departmen` FOREIGN KEY (`employee_department_id`) REFERENCES `department_database_table` (`department_code`)
) ENGINE=InnoDB AUTO_INCREMENT=44 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user_database_table`
--

LOCK TABLES `user_database_table` WRITE;
/*!40000 ALTER TABLE `user_database_table` DISABLE KEYS */;
INSERT INTO `user_database_table` VALUES (1,'A00039','向清河','active','13507185366','铁机路B4','车辆首席专家','JTGSLD',0),(2,'A00052','朱东飞','active','13871044858','铁机路B10','子公司专职外部董事','JTGSLD',0),(3,'A00427','温裕春','active','13607192206','铁机路B10','土建首席专家','JTGSLD',0),(5,'A00002','王金峰','active','13971670655','铁机路B17A','集团总经理','JTGSLD',0),(6,'A00016','叶万敏','retirement','18627160958','铁机路B16','已退休','JTGSLD',0),(7,'A00026','张汉云','active','13607175376','铁机路B16','集团纪检书记','JTGSLD',0),(8,'A00036','肖浩然','left','13986086039','铁机路B16','已调走','JTGSLD',0),(9,'A00631','盛永清','active','15902772006','铁机路B16','集团副总','JTGSLD',0),(10,'A00040','刘亚娟','active','15927025129','铁机路B16','集团副总、总经济师','JTGSLD',0),(11,'A00012','马君瑞','retirement','18627160738','铁机路B16','已退休','JTGSLD',0),(12,'A00046','乔炜','active','13808680861','铁机路B10','信息管理中心主任','JTXXGLZX',0),(13,'A02349','张政','active','15927567278','铁机路B10','员工','JTXXGLZX',0),(14,'A05182','程亮','active','15827488853','铁机路B10','员工','JTXXGLZX',0),(15,'A04047','张永福','active','15972225667','铁机路B10','员工','JTXXGLZX',0),(16,'A13082','吴培培','active','18986183920','铁机路B10','员工','JTXXGLZX',0),(17,'A00981','蔡明磊','active','13886014621','铁机路B10','员工','JTXXGLZX',0),(18,'A15160','刘文沛','active','18627041789','铁机路B10','员工','JTXXGLZX',0),(20,'A04010','邱珊','active','15827070993','铁机路B6','员工','JTSJFKB',0),(21,'A15740','徐振韬','active','18086081690','铁机路B6','员工','JTSJFKB',0),(22,'A00682','陶文涛','active','13607158409','铁机路B6','技术管理中心副主任','JTJSGLZX',0),(23,'A01797','朱群俊','active','18607155616','铁机路B6','员工','JTJSGLZX',0),(24,'A00476','陶懿','active','15927635332','铁机路B6','员工','JTJSGLZX',0),(25,'A05163','吴忠坦','active','18672350130','铁机路B6','员工','JTJSGLZX',0),(26,'A10713','何李','active','13886080414','铁机路B6','员工','JTJSGLZX',0),(27,'A11033','黎寰','active','13667138203','铁机路B6','员工','JTJSGLZX',0),(28,'A08963','裴进','active','13407172799','铁机路B6','员工','JTJSGLZX',0),(29,'A10685','邓志强','active','13296621686','铁机路B6','员工','JTJSGLZX',0),(30,'A13383','凌诚昊','active','18986000516','铁机路B6','员工','JTJSGLZX',0),(31,'A13515','周立','active','18163500809','铁机路B6','员工','JTJSGLZX',0),(32,'A00436','刘彦均','active','13986262921','铁机路B6','员工','JTJSGLZX',0),(33,'A00875','林梓','active','13971115282','铁机路B6','员工','JTJSGLZX',0),(34,'A00646','夏银飞','active','13871190540','铁机路B6','员工','JTJSGLZX',0),(35,'A00842','张冰','active','13886182861','铁机路B9','财务部副部长','JTCWB',0),(36,'A02130','黄力','active','13797011412','铁机路B9','财务部副部长','JTCWB',0),(37,'A05119','苏圣群','active','15007163501','铁机路B9','员工','JTCWB',0),(38,'A03947','龙秀','active','15207179813','铁机路B9','员工','JTCWB',0),(39,'A13357','彭子文','active','13554392215','铁机路B9','员工','JTCWB',0),(40,'A15408','王超','active','13995526053','铁机路B9','员工','JTCWB',0),(41,'A09058','胡超峰','active','15623012510','铁机路B9','员工','JTCWB',0),(43,'A03949','彭长城','active','13297050000','B10','职员','JTXXGLZX',0);
/*!40000 ALTER TABLE `user_database_table` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping routines for database 'asset_management_backend'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-06-10 19:41:55
