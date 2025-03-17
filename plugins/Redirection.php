<?php

class RedirectionPlugin extends Plugin
{
    protected $pluginPath = "redirection/redirection.php";

    private $redirectionOptions = array (
        'support' => false,
        'token' => '',                 # leave blank to regenerate
        'monitor_post' => 1,
        'monitor_types' => 
            array (
                0 => 'post',
                1 => 'page',
            ),
        'associated_redirect' => '',
        'auto_target' => '',
        'expire_redirect' => 7,
        'expire_404' => 7,
        'log_external' => false,
        'log_header' => false,
        'track_hits' => true,
        'modules' => 
            array (
            ),
        'redirect_cache' => 1,
        'ip_logging' => 0,
        'ip_headers' => 
            array (
            ),
        'ip_proxy' => 
            array (
            ),
        'last_group_id' => 1,
        'rest_api' => 0,
        'https' => false,
        'headers' => 
            array (
            ),
        'database' => '4.2',
        'relocate' => '',
        'preferred_domain' => '',
        'aliases' => 
            array (
            ),
        'permalinks' => 
            array (
            ),
        'cache_key' => 0,
        'plugin_update' => 'prompt',
        'update_notice' => 0,
        'flag_query' => 'exact',
        'flag_case' => true,
        'flag_trailing' => true,
        'flag_regex' => false,
    );

    public function addSpecialConfiguration()
    {
        $this->createRedirectionTables();
    }

    public function updateOptions()
    {
        update_option('redirection_options', $this->redirectionOptions);
    }

    private function createRedirectionTables()
    {
        $table_items = "wp_redirection_items";
        $table_groups = "wp_redirection_groups";
        $table_logs = "wp_redirection_logs";
        $table_404 = "wp_redirection_404";

        $sqls = [
            "items" => "CREATE TABLE IF NOT EXISTS `{$table_items}` (
                `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
                `url` mediumtext NOT NULL,
                `match_url` VARCHAR(2000) DEFAULT NULL,
                `match_data` TEXT,
                `regex` INT(11) unsigned NOT NULL DEFAULT '0',
                `position` INT(11) unsigned NOT NULL DEFAULT '0',
                `last_count` INT(10) unsigned NOT NULL DEFAULT '0',
                `last_access` datetime NOT NULL DEFAULT '1970-01-01 00:00:00',
                `group_id` INT(11) NOT NULL DEFAULT '0',
                `status` enum('enabled','disabled') NOT NULL DEFAULT 'enabled',
                `action_type` VARCHAR(20) NOT NULL,
                `action_code` INT(11) unsigned NOT NULL,
                `action_data` MEDIUMTEXT,
                `match_type` VARCHAR(20) NOT NULL,
                `title` TEXT,
                PRIMARY KEY (`id`),
                KEY `url` (`url`(191)),
                KEY `status` (`status`),
                KEY `regex` (`regex`),
                KEY `group_idpos` (`group_id`, `position`),
                KEY `group` (`group_id`),
                KEY `match_url` (`match_url`(191))
              ) DEFAULT CHARACTER SET utf8mb4 COLLATE=utf8mb4_unicode_520_ci;",

            "groups" => "CREATE TABLE IF NOT EXISTS `{$table_groups}` (
                `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
                `name` VARCHAR(50) NOT NULL,
                `tracking` INT(11) NOT NULL DEFAULT '1',
                `module_id` INT(11) unsigned NOT NULL DEFAULT '0',
                `status` enum('enabled','disabled') NOT NULL DEFAULT 'enabled',
                `position` INT(11) unsigned NOT NULL DEFAULT '0',
                PRIMARY KEY (`id`),
                KEY `module_id` (`module_id`),
                KEY `status` (`status`)
              ) DEFAULT CHARACTER SET utf8mb4 COLLATE=utf8mb4_unicode_520_ci;",

            "logs" => "CREATE TABLE IF NOT EXISTS `{$table_logs}` (
                `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
                `created` datetime NOT NULL,
                `url` MEDIUMTEXT NOT NULL,
                `domain` VARCHAR(255) DEFAULT NULL,
                `sent_to` MEDIUMTEXT,
                `agent` MEDIUMTEXT,
                `referrer` MEDIUMTEXT,
                `http_code` INT(11) unsigned NOT NULL DEFAULT '0',
                `request_method` VARCHAR(10) DEFAULT NULL,
                `request_data` MEDIUMTEXT,
                `redirect_by` VARCHAR(50) DEFAULT NULL,
                `redirection_id` INT(11) unsigned DEFAULT NULL,
                `ip` VARCHAR(45) DEFAULT NULL,
                PRIMARY KEY (`id`),
                KEY `created` (`created`),
                KEY `redirection_id` (`redirection_id`),
                KEY `ip` (`ip`)
              ) DEFAULT CHARACTER SET utf8mb4 COLLATE=utf8mb4_unicode_520_ci;",

            "404" => "CREATE TABLE IF NOT EXISTS `{$table_404}` (
                `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
                `created` datetime NOT NULL,
                `url` MEDIUMTEXT NOT NULL,
                `domain` VARCHAR(255) DEFAULT NULL,
                `agent` VARCHAR(255) DEFAULT NULL,
                `referrer` VARCHAR(255) DEFAULT NULL,
                `http_code` INT(11) unsigned NOT NULL DEFAULT '0',
                `request_method` VARCHAR(10) DEFAULT NULL,
                `request_data` MEDIUMTEXT,
                `ip` VARCHAR(45) DEFAULT NULL,
                PRIMARY KEY (`id`),
                KEY `created` (`created`),
                KEY `referrer` (`referrer`(191)),
                KEY `ip` (`ip`)
              ) DEFAULT CHARACTER SET utf8mb4 COLLATE=utf8mb4_unicode_520_ci;",
            
            "insert" => "INSERT INTO `{$table_groups}` (id,name,tracking,module_id,status,`position`) VALUES
                (1,'Redirections',1,1,'enabled',0),
                (2,'Modified Posts',1,1,'enabled',1);",
        ];
    
        dbDelta($sqls["items"]);
        dbDelta($sqls["groups"]);
        dbDelta($sqls["logs"]);
        dbDelta($sqls["404"]);
        dbDelta($sqls["insert"]);
    }
}