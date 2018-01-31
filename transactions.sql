CREATE TABLE `transactions` (
    `timestamp` INT(11) UNSIGNED NULL DEFAULT NULL,
    `ip` INT(11) UNSIGNED NULL DEFAULT NULL,
    `target` INT(11) UNSIGNED NULL DEFAULT NULL,
    `direction` CHAR(4) NULL DEFAULT NULL,
    `switch` CHAR(32) NULL DEFAULT NULL,
    `name` CHAR(32) NULL DEFAULT NULL,
    `hash` CHAR(32) NULL DEFAULT NULL
)
COLLATE='latin1_swedish_ci'
ENGINE=InnoDB
;