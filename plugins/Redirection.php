<?php

class RedirectionPlugin extends Plugin
{
    protected $pluginPath = "redirection/redirection.php";

    private $redirectionOptions = array(
        'monitor_post_changes' => false,
        'auto_redirects' => true,
        'track_404' => true,
        'disable_canonical' => false,
        'installer' => false,
        'permalinks' => true,
        'logging' => false,
        'database_version' => 20,
        'notices' => false
    );

    private $redirection_wizard_complete = true;
    private $redirection_permalinks = true;
    private $redirection_items_per_page = 100;
    private $redirection_404_logs = false;

    public function addSpecialConfiguration()
    {
        global $wpdb;

        error_log("[RedirectionPlugin] Activating special configuration...");

        if (!is_plugin_active($this->pluginPath)) {
            error_log("[RedirectionPlugin] Activating the plugin...");
            $activatedPlugin = activate_plugin($this->pluginPath);
            if ($activatedPlugin instanceof WP_Error) {
                throw new ErrorException(var_export($activatedPlugin->errors, true) . " - " . $this->pluginPath);
            }
        }

        error_log("[RedirectionPlugin] Plugin activated successfully.");

        $this->createRedirectionTables($wpdb);
        $this->updateOptions();
        $this->importRedirectionsFromOperator($wpdb);
    }

    public function updateOptions()
    {
        update_option('redirection_options', $this->redirectionOptions);
        update_option('redirection_wizard_complete', $this->redirection_wizard_complete);
        update_option('redirection_permalinks', $this->redirection_permalinks);
        update_option('redirection_items_per_page', $this->redirection_items_per_page);
        update_option('redirection_404_logs', $this->redirection_404_logs);
        update_option('redirection_installed', true);
        update_option('redirection_activation_flag', false);

        $options_check = get_option('redirection_options');
        if ($options_check) {
            error_log("[RedirectionPlugin] Redirection options updated successfully!");
        } else {
            error_log("[RedirectionPlugin] ERROR: Redirection options were not saved!");
        }
    }

    private function createRedirectionTables($wpdb)
    {
        require_once ABSPATH . 'wp-admin/includes/upgrade.php';

        $charset_collate = $wpdb->get_charset_collate();
        $table_name = $wpdb->prefix . "redirection_items";

        $sql = "
        CREATE TABLE IF NOT EXISTS $table_name (
            id INT(11) UNSIGNED NOT NULL AUTO_INCREMENT,
            url MEDIUMTEXT NOT NULL,
            match_url VARCHAR(2000) DEFAULT NULL,
            match_data TEXT,
            regex INT(11) UNSIGNED NOT NULL DEFAULT '0',
            position INT(11) UNSIGNED NOT NULL DEFAULT '0',
            last_count INT(10) UNSIGNED NOT NULL DEFAULT '0',
            last_access DATETIME NOT NULL DEFAULT '1970-01-01 00:00:00',
            group_id INT(11) NOT NULL DEFAULT '0',
            status ENUM('enabled','disabled') NOT NULL DEFAULT 'enabled',
            action_type VARCHAR(20) NOT NULL,
            action_code INT(11) UNSIGNED NOT NULL,
            action_data MEDIUMTEXT,
            match_type VARCHAR(20) NOT NULL,
            title TEXT,
            PRIMARY KEY (id),
            KEY url (url(191)),
            KEY status (status),
            KEY regex (regex),
            KEY group_idpos (group_id, position),
            KEY group (group_id),
            KEY match_url (match_url(191))
        ) $charset_collate;
        ";

        error_log("[RedirectionPlugin] Creating redirection table...");
        dbDelta($sql);

        $table_exists = $wpdb->get_var("SHOW TABLES LIKE '$table_name'");
        if ($table_exists) {
            error_log("[RedirectionPlugin] Redirection table created successfully!");
        } else {
            error_log("[RedirectionPlugin] ERROR: Redirection table was not created!");
        }
    }

    public function importRedirectionsFromOperator($wpdb)
    {
        $file_path = '/etc/wordpress/redirections.json';

        if (!file_exists($file_path)) {
            error_log("[RedirectionPlugin] Redirection file not found: $file_path");
            return;
        }

        $redirections = json_decode(file_get_contents($file_path), true);
        if (empty($redirections)) {
            error_log("[RedirectionPlugin] No valid redirections found in $file_path.");
            return;
        }

        $table_name = $wpdb->prefix . "redirection_items";

        foreach ($redirections as $redirect) {
            $source = sanitize_text_field($redirect['source']);
            $target = sanitize_text_field($redirect['target']);
            $regex = isset($redirect['regex']) && $redirect['regex'] ? 1 : 0;

            $wpdb->query(
                $wpdb->prepare(
                    "INSERT INTO $table_name (url, match_url, regex, status, action_type, action_code)
                    VALUES (%s, %s, %d, 'enabled', 'url', 301)",
                    $source, $target, $regex
                )
            );

            if ($wpdb->last_error) {
                error_log("[RedirectionPlugin] MySQL Error: " . $wpdb->last_error);
            }
        }

        error_log("[RedirectionPlugin] Redirections successfully imported from $file_path.");
    }
}
