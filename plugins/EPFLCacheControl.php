<?php

class EPFLCacheControl extends Plugin
{
	protected $pluginPath = "epfl-cache-control/epfl-cache-control.php";
	private $cache_control_front_page_max_age = 300;
	private $cache_control_pages_max_age = 300;
	private $cache_control_categories_max_age = 300;
	private $cache_control_singles_max_age = 300;
	private $cache_control_home_max_age = 300;
	private $cache_control_tags_max_age = 300;
	private $cache_control_authors_max_age = 300;
	private $cache_control_dates_max_age = 300;
	private $cache_control_feeds_max_age = 300;
	private $cache_control_attachment_max_age = 300;
	private $cache_control_search_max_age = 300;
	private $cache_control_notfound_max_age = 300;
	private $cache_control_redirect_permanent_max_age = 300;
}
